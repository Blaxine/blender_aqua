"""Pure-Python numerical regression checks; no Blender, bakes or renders."""
import importlib.util
import math
import pathlib
import random
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('aqs_wave_math', ROOT / 'gerstner.py')
waves = importlib.util.module_from_spec(spec)
spec.loader.exec_module(waves)


class FilterTests(unittest.TestCase):
    def test_matches_original_fir_in_arbitrary_frame_order(self):
        rng = random.Random(42)
        for _ in range(1500):
            layers = waves.layer_params(rng.uniform(0, 3), rng.uniform(.1, 50),
                                        rng.uniform(-360, 360), rng.random(),
                                        rng.uniform(-2, 4), rng.random())
            x, y, t = (rng.uniform(-100, 100) for _ in range(3))
            smoothing = rng.uniform(.00001, 2)
            expected = sum(w * waves.height(layers, x, y, t - j * smoothing / waves._FIR_K)
                           for j, w in enumerate(waves._FIR_W)) / waves._FIR_NORM
            self.assertTrue(math.isclose(expected, waves.smoothed_height(layers, x, y, t, smoothing),
                                         rel_tol=1e-9, abs_tol=1e-10))

    def test_unsmoothed_and_zero_speed(self):
        layers = waves.layer_params(1, 10, 0, .5, 0, .2)
        for smoothing in (0, 1e-7, .2, 2):
            self.assertAlmostEqual(waves.height(layers, 3, 7, 40),
                                   waves.smoothed_height(layers, 3, 7, 40, smoothing), places=12)

    def test_cache_does_not_grow_with_animation_length(self):
        layers = waves.layer_params(1, 10, 0, .5, 1, .2)
        waves._filtered_layers.cache_clear()
        for i in range(1000):
            waves.smoothed_height(layers, 0, 0, i, i / 1000 + .01)
        self.assertLessEqual(waves._filtered_layers.cache_info().currsize, 256)


if __name__ == '__main__':
    unittest.main()
