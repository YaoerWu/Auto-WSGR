import image_autowsgrs
import numpy as np


class ApiDll:
    def locate(self, image: np.ndarray) -> list[tuple[int, int]]:
        return image_autowsgrs.locate(image)

    def recognize_enemy(self, images: list[np.ndarray]) -> str:
        return image_autowsgrs.recognize_enemy(images)

    def recognize_map(self, image: np.ndarray) -> str:
        return image_autowsgrs.recognize_map(image)
