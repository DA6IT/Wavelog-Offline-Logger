//go:build windows

package main

import (
	"crypto/sha256"
	"embed"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

const (
	appVersion   = "0.12.0-rc1"
	pythonURL    = "https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
	pythonSHA256 = "67b5635e80ea51072b87941312d00ec8927c4db9ba18938f7ad2d27b328b95fb"

	JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
	JobObjectExtendedLimitInformation  = 9
	PROCESS_SET_QUOTA                  = 0x0100
	PROCESS_TERMINATE                  = 0x0001
)

//go:embed app.py
var appSource []byte

//go:embed logger_core.py
var coreSource []byte

//go:embed cat_control.py
var catSource []byte

//go:embed update_check.py
var updateCheckSource []byte

//go:embed cty.dat
var ctyData []byte

// Hamlib is prepared by scripts/prepare-hamlib-windows.ps1 before go build.
// The official archive is pinned and SHA-256 verified by that script.
//
//go:embed build/embedded/hamlib/windows-x64/*
var hamlibFS embed.FS

var hamlibFileNames = []string{
	"rigctld.exe",
	"libhamlib-4.dll",
	"libusb-1.0.dll",
	"libgcc_s_seh-1.dll",
	"libwinpthread-1.dll",
	"COPYING.txt",
	"COPYING.LIB.txt",
	"LICENSE.txt",
	"AUTHORS.txt",
	"README.md.txt",
	"README.w64-bin.txt",
	"HAMLIB_VERSION.txt",
}

type IO_COUNTERS struct {
	ReadOperationCount, WriteOperationCount, OtherOperationCount uint64
	ReadTransferCount, WriteTransferCount, OtherTransferCount    uint64
}

type JOBOBJECT_BASIC_LIMIT_INFORMATION struct {
	PerProcessUserTimeLimit int64
	PerJobUserTimeLimit     int64
	LimitFlags              uint32
	MinimumWorkingSetSize   uintptr
	MaximumWorkingSetSize   uintptr
	ActiveProcessLimit      uint32
	Affinity                uintptr
	PriorityClass           uint32
	SchedulingClass         uint32
}

type JOBOBJECT_EXTENDED_LIMIT_INFORMATION struct {
	BasicLimitInformation JOBOBJECT_BASIC_LIMIT_INFORMATION
	IoInfo                IO_COUNTERS
	ProcessMemoryLimit    uintptr
	JobMemoryLimit        uintptr
	PeakProcessMemoryUsed uintptr
	PeakJobMemoryUsed     uintptr
}

var (
	kernel32                     = syscall.NewLazyDLL("kernel32.dll")
	procCreateJobObjectW         = kernel32.NewProc("CreateJobObjectW")
	procSetInformationJobObject  = kernel32.NewProc("SetInformationJobObject")
	procAssignProcessToJobObject = kernel32.NewProc("AssignProcessToJobObject")
	procOpenProcess              = kernel32.NewProc("OpenProcess")
	procCloseHandle              = kernel32.NewProc("CloseHandle")
)

func messageBox(title, text string, flags uintptr) {
	user32 := syscall.NewLazyDLL("user32.dll")
	proc := user32.NewProc("MessageBoxW")
	t, _ := syscall.UTF16PtrFromString(title)
	x, _ := syscall.UTF16PtrFromString(text)
	proc.Call(0, uintptr(unsafe.Pointer(x)), uintptr(unsafe.Pointer(t)), flags)
}

func download(url, target string) error {
	client := &http.Client{Timeout: 5 * time.Minute}
	resp, err := client.Get(url)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("HTTP %d", resp.StatusCode)
	}
	f, err := os.Create(target)
	if err != nil {
		return err
	}
	_, copyErr := io.Copy(f, resp.Body)
	closeErr := f.Close()
	if copyErr != nil {
		return copyErr
	}
	return closeErr
}

func verifySHA256(path string) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	h := sha256.New()
	if _, err := io.Copy(h, f); err != nil {
		return err
	}
	got := hex.EncodeToString(h.Sum(nil))
	if !strings.EqualFold(got, pythonSHA256) {
		return fmt.Errorf("Pruefsumme stimmt nicht (erhalten %s)", got)
	}
	return nil
}

func ensurePython(runtimeDir string) error {
	pythonw := filepath.Join(runtimeDir, "pythonw.exe")
	if _, err := os.Stat(pythonw); err == nil {
		return nil
	}

	messageBox("DA6IT.de Wavelog Offline Logger",
		"Beim ersten Start wird einmalig die offizielle Python-Laufzeit von python.org geladen.\n\n"+
			"Sie wird ausschließlich privat unter deinem Windows-Benutzerprofil fuer DA6IT.de eingerichtet. "+
			"Es wird nichts in PATH eingetragen und kein systemweites Python benoetigt.\n\n"+
			"Danach funktioniert das Offline-Logging ohne Internet.", 0x40)

	_ = os.RemoveAll(runtimeDir)
	if err := os.MkdirAll(runtimeDir, 0755); err != nil {
		return err
	}

	installer := filepath.Join(os.TempDir(), "da6it-python-3.12.10-amd64.exe")
	defer os.Remove(installer)
	if err := download(pythonURL, installer); err != nil {
		return fmt.Errorf("Python-Download fehlgeschlagen: %w", err)
	}
	if err := verifySHA256(installer); err != nil {
		return fmt.Errorf("Python-Download ungueltig: %w", err)
	}

	args := []string{
		"/quiet",
		"InstallAllUsers=0",
		"TargetDir=" + runtimeDir,
		"Include_launcher=0",
		"InstallLauncherAllUsers=0",
		"AssociateFiles=0",
		"Shortcuts=0",
		"PrependPath=0",
		"Include_test=0",
		"Include_doc=0",
		"Include_pip=0",
		"Include_tcltk=1",
		"Include_dev=0",
		"Include_debug=0",
	}
	cmd := exec.Command(installer, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if out, err := cmd.CombinedOutput(); err != nil {
		return fmt.Errorf("Python-Laufzeit konnte nicht eingerichtet werden: %v (%s)", err, string(out))
	}
	if _, err := os.Stat(pythonw); err != nil {
		return fmt.Errorf("pythonw.exe fehlt nach der Einrichtung")
	}

	// Verify that the modules needed by the desktop app are present.
	check := exec.Command(filepath.Join(runtimeDir, "python.exe"), "-c", "import tkinter, sqlite3; print('ok')")
	check.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}
	if out, err := check.CombinedOutput(); err != nil {
		return fmt.Errorf("Python-Desktopmodule fehlen: %v (%s)", err, string(out))
	}
	return nil
}

func writeAppFiles(appDir string) error {
	if err := os.MkdirAll(appDir, 0755); err != nil {
		return err
	}
	versionPath := filepath.Join(appDir, "VERSION")
	oldVersion, _ := os.ReadFile(versionPath)
	hamlibDir := filepath.Join(appDir, "hamlib")
	if strings.TrimSpace(string(oldVersion)) == appVersion && appFilesComplete(appDir, hamlibDir) {
		return nil
	}
	if err := os.WriteFile(filepath.Join(appDir, "app.py"), appSource, 0644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(appDir, "logger_core.py"), coreSource, 0644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(appDir, "cat_control.py"), catSource, 0644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(appDir, "update_check.py"), updateCheckSource, 0644); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(appDir, "cty.dat"), ctyData, 0644); err != nil {
		return err
	}
	if err := os.MkdirAll(hamlibDir, 0755); err != nil {
		return err
	}
	for _, name := range hamlibFileNames {
		embeddedPath := "build/embedded/hamlib/windows-x64/" + name
		data, err := hamlibFS.ReadFile(embeddedPath)
		if err != nil {
			return fmt.Errorf("Hamlib-Datei %s fehlt im Build: %w", name, err)
		}
		mode := os.FileMode(0644)
		if strings.HasSuffix(strings.ToLower(name), ".exe") {
			mode = 0755
		}
		if err := os.WriteFile(filepath.Join(hamlibDir, name), data, mode); err != nil {
			return err
		}
	}
	return os.WriteFile(versionPath, []byte(appVersion+"\n"), 0644)
}

func appFilesComplete(appDir, hamlibDir string) bool {
	required := []string{
		filepath.Join(appDir, "app.py"),
		filepath.Join(appDir, "logger_core.py"),
		filepath.Join(appDir, "cat_control.py"),
		filepath.Join(appDir, "update_check.py"),
		filepath.Join(appDir, "cty.dat"),
	}
	for _, name := range hamlibFileNames {
		required = append(required, filepath.Join(hamlibDir, name))
	}
	for _, path := range required {
		if info, err := os.Stat(path); err != nil || info.IsDir() || info.Size() == 0 {
			return false
		}
	}
	return true
}

func createKillJob() uintptr {
	h, _, _ := procCreateJobObjectW.Call(0, 0)
	if h == 0 {
		return 0
	}
	info := JOBOBJECT_EXTENDED_LIMIT_INFORMATION{}
	info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
	r, _, _ := procSetInformationJobObject.Call(
		h,
		JobObjectExtendedLimitInformation,
		uintptr(unsafe.Pointer(&info)),
		unsafe.Sizeof(info),
	)
	if r == 0 {
		procCloseHandle.Call(h)
		return 0
	}
	return h
}

func assignPidToJob(job uintptr, pid int) bool {
	if job == 0 {
		return false
	}
	ph, _, _ := procOpenProcess.Call(PROCESS_SET_QUOTA|PROCESS_TERMINATE, 0, uintptr(uint32(pid)))
	if ph == 0 {
		return false
	}
	defer procCloseHandle.Call(ph)
	r, _, _ := procAssignProcessToJobObject.Call(job, ph)
	return r != 0
}

func main() {
	local := os.Getenv("LOCALAPPDATA")
	if local == "" {
		home, _ := os.UserHomeDir()
		local = home
	}
	base := filepath.Join(local, "AFU-Tools", "WavelogOfflineLogger")
	runtimeDir := filepath.Join(base, "runtime", "python312")
	appDir := filepath.Join(base, "app-v0120-rc1")

	if err := writeAppFiles(appDir); err != nil {
		messageBox("DA6IT.de Logger - Startfehler", "Programmdateien konnten nicht vorbereitet werden:\n"+err.Error(), 0x10)
		return
	}
	if err := ensurePython(runtimeDir); err != nil {
		messageBox("DA6IT.de Logger - Startfehler", err.Error()+"\n\nBeim naechsten Start wird erneut versucht.", 0x10)
		return
	}

	pythonw := filepath.Join(runtimeDir, "pythonw.exe")
	appPath := filepath.Join(appDir, "app.py")
	cmd := exec.Command(pythonw, appPath)
	cmd.Dir = appDir
	cmd.Env = append(os.Environ(), "PYTHONUTF8=1", "PYTHONDONTWRITEBYTECODE=1")
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true}

	job := createKillJob()
	if job != 0 {
		defer procCloseHandle.Call(job)
	}

	if err := cmd.Start(); err != nil {
		messageBox("DA6IT.de Logger - Startfehler", "Desktop-App konnte nicht gestartet werden:\n"+err.Error(), 0x10)
		return
	}
	if job != 0 {
		_ = assignPidToJob(job, cmd.Process.Pid)
	}

	// Keep the invisible launcher alive while the desktop application runs.
	// Closing the app ends pythonw; closing/crashing the launcher closes the job and kills pythonw.
	err := cmd.Wait()
	if err != nil {
		logPath := filepath.Join(base, "startup.log")
		messageBox("DA6IT.de Logger", "Die Anwendung wurde unerwartet beendet.\n\nDetails stehen ggf. in:\n"+logPath, 0x10)
	}
}
