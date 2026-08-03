import numpy as np
from autowsgr_native.recognition import locate, recognize_enemy, recognize_map


class ApiDll:
    def locate(self, image: np.ndarray) -> list[list[int]]:
        return locate(image)

    def recognize_enemy(self, images: list[np.ndarray]) -> str:
        return recognize_enemy(images)

    def recognize_map(self, image: np.ndarray) -> str:
        return recognize_map(image)
