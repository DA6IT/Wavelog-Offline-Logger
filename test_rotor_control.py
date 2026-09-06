from __future__ import annotations

import socket
import time
import unittest

from rotor_control import (
    DUMMY_ROTOR_MODEL_ID,
    RotorConfig,
    RotatorManager,
    build_rotctld_args,
    find_rotctld,
    parse_rotctld_models,
)


class RotorControlTests(unittest.TestCase):
    def test_config_roundtrip(self):
        config = RotorConfig(
            model_id=401,
            device="COM7",
            baud=9600,
            port=4533,
            poll_interval_ms=750,
        )
        settings = config.settings()
        restored = RotorConfig.from_getter(lambda key, default="": settings.get(key, default))
        self.assertEqual(restored, config)
        restored.validate()

    def test_dummy_args_bind_loopback(self):
        config = RotorConfig(model_id=DUMMY_ROTOR_MODEL_ID, port=4543)
        args = build_rotctld_args(config)
        self.assertEqual(args[:2], ["-m", "1"])
        self.assertIn("-T", args)
        self.assertEqual(args[args.index("-T") + 1], "127.0.0.1")
        self.assertEqual(args[args.index("-t") + 1], "4543")
        self.assertNotIn("-r", args)

    def test_model_parser_filters_net_backend(self):
        output = """
   1  Hamlib                 Dummy                   20240101.0      Stable      ROT_MODEL_DUMMY
   2  Hamlib                 NET rotctl              20240101.0      Stable      ROT_MODEL_NETROTCTL
 401  Idiom Press            RotorEZ                 20240101.0      Stable      ROT_MODEL_ROTOREZ
"""
        models = parse_rotctld_models(output)
        self.assertEqual([model.model_id for model in models], [1, 401])
        self.assertIn("Dummy", models[0].label)

    def test_dummy_rotctld_integration_when_available(self):
        try:
            executable = find_rotctld()
        except Exception as exc:
            self.skipTest(f"rotctld not prepared yet: {exc}")

        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
        probe.close()

        manager = RotatorManager(executable)
        try:
            manager.start(RotorConfig(model_id=1, port=port), timeout=5.0)

            # Hamlib's Dummy backend intentionally simulates physical rotor
            # movement at about 360 degrees/minute instead of teleporting to
            # the requested position. Verify that it actually moves and
            # reaches a nearby target within a bounded time.
            start = manager.read()
            manager.set_position(3.0, 0.0)

            deadline = time.monotonic() + 2.0
            samples = []
            reading = start
            while time.monotonic() < deadline:
                time.sleep(0.05)
                reading = manager.read()
                samples.append(reading.azimuth % 360.0)
                if abs((reading.azimuth % 360.0) - 3.0) <= 0.25:
                    break

            self.assertTrue(samples)
            self.assertGreater(max(samples), start.azimuth % 360.0)
            self.assertAlmostEqual(reading.azimuth % 360.0, 3.0, delta=0.25)

            # STOP must freeze the simulated rotor at its current position.
            manager.set_position(30.0, 0.0)
            time.sleep(0.20)
            manager.stop_motion()
            stopped = manager.read()
            time.sleep(0.25)
            after_stop = manager.read()
            self.assertAlmostEqual(
                after_stop.azimuth % 360.0,
                stopped.azimuth % 360.0,
                delta=0.10,
            )
        finally:
            manager.stop()


if __name__ == "__main__":
    unittest.main()
