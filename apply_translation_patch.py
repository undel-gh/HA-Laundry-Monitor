"""Patch Laundry Monitor translations for state-machine completion.

Run from the repository root:
    python apply_translation_patch.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

TRANSLATION_DIR = Path(
    "custom_components/laundry_monitor/translations"
)

PATCHES: dict[str, dict[str, Any]] = {
    "en": {
        "config_description": (
            "Select the Home Assistant entities used to monitor this "
            "washing machine. The power sensor is required; door and "
            "vibration sensors are recommended but optional."
        ),
        "door_description": (
            "Optional. Used for door-based arming and diagnostic events."
        ),
        "vibration_description": (
            "Optional. Improves probable final-spin detection. Power-only "
            "cycle completion remains available without it."
        ),
        "options_description": (
            "Configure detector thresholds, finish fallbacks, lifecycle "
            "timeouts, required-source tolerance, and snapshot recovery."
        ),
        "data": {
            "running_finish_confirmation": (
                "Power-only finish confirmation"
            ),
            "arming_timeout": "Arming timeout",
            "finished_retention": "Finished-state retention",
            "power_unavailable_grace": (
                "Power sensor unavailable grace period"
            ),
            "snapshot_max_age": "Maximum active snapshot age",
        },
        "data_description": {
            "running_finish_confirmation": (
                "How long meaningful power activity must remain absent "
                "before running changes directly to finished when final "
                "spin is unavailable or not detected."
            ),
            "arming_timeout": (
                "How long the optional armed state may remain active after "
                "a door-close event. Use 0 for an immediate reset."
            ),
            "finished_retention": (
                "How long finished remains visible before returning to idle "
                "when Laundry Tracking is disabled."
            ),
            "power_unavailable_grace": (
                "How long the required power sensor may remain missing, "
                "unknown, invalid, or unavailable before entering error."
            ),
            "snapshot_max_age": (
                "Maximum age of a running or final-spin snapshot that may "
                "be restored after Home Assistant restarts."
            ),
        },
    },
    "ru": {
        "config_description": (
            "Выберите сущности Home Assistant для мониторинга этой "
            "стиральной машины. Датчик мощности обязателен; датчики двери "
            "и вибрации рекомендуются, но не являются обязательными."
        ),
        "door_description": (
            "Необязательно. Используется для постановки в состояние "
            "готовности по закрытию двери и диагностических событий."
        ),
        "vibration_description": (
            "Необязательно. Улучшает распознавание вероятного финального "
            "отжима. Завершение только по мощности работает и без него."
        ),
        "options_description": (
            "Настройте пороги детекторов, резервное определение завершения, "
            "таймауты жизненного цикла, допуск недоступности датчика "
            "мощности и восстановление snapshot."
        ),
        "data": {
            "running_finish_confirmation": (
                "Подтверждение завершения только по мощности"
            ),
            "arming_timeout": "Таймаут состояния готовности",
            "finished_retention": (
                "Время отображения состояния «Завершено»"
            ),
            "power_unavailable_grace": (
                "Допуск недоступности датчика мощности"
            ),
            "snapshot_max_age": (
                "Максимальный возраст активного snapshot"
            ),
        },
        "data_description": {
            "running_finish_confirmation": (
                "Сколько времени должна отсутствовать значимая активность "
                "по мощности, чтобы перейти из running непосредственно в "
                "finished, если финальный отжим недоступен или не распознан."
            ),
            "arming_timeout": (
                "Как долго состояние готовности может сохраняться после "
                "закрытия двери. Значение 0 выполняет немедленный сброс."
            ),
            "finished_retention": (
                "Как долго состояние finished остаётся видимым перед "
                "возвратом в idle, когда отслеживание белья выключено."
            ),
            "power_unavailable_grace": (
                "Как долго обязательный датчик мощности может отсутствовать "
                "или находиться в состоянии unknown/unavailable до перехода "
                "в error."
            ),
            "snapshot_max_age": (
                "Максимальный возраст snapshot состояния running или "
                "final_spin, разрешённого для восстановления после "
                "перезапуска Home Assistant."
            ),
        },
    },
}


def _patch_language(language: str, patch: dict[str, Any]) -> None:
    """Apply one language patch."""
    path = TRANSLATION_DIR / f"{language}.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    for step_id in ("user", "reconfigure"):
        step = data["config"]["step"][step_id]
        step["description"] = patch["config_description"]
        step["data_description"]["door_sensor"] = (
            patch["door_description"]
        )
        step["data_description"]["vibration_sensor"] = (
            patch["vibration_description"]
        )

    options = data["options"]["step"]["init"]
    options["description"] = patch["options_description"]
    options["data"].update(patch["data"])
    options["data_description"].update(patch["data_description"])

    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Patch every supported language."""
    for language, patch in PATCHES.items():
        _patch_language(language, patch)
        print(f"Updated {language}.json")


if __name__ == "__main__":
    main()
