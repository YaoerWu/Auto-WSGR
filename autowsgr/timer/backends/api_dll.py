import autowsgr_native
import numpy as np


class ApiDll:
    def locate(self, image: np.ndarray) -> list[tuple[int, int]]:
        return autowsgr_native.locate(image)

    def recognize_enemy(self, images: list[np.ndarray]) -> str:
        return autowsgr_native.recognize_enemy(images)

    def recognize_map(self, image: np.ndarray) -> str:
        return autowsgr_native.recognize_map(image)
