# Словарь переводов с учетом падежей
MODEL_NAMES_TRANSLATION = {
    "log entry": "записи журнала",
    "permission": "разрешения",
    "group": "группы",
    "user": "пользователя",
    "content type": "типа содержимого",
    "session": "сессии",
    "achievement": "достижения",
    "classifications": "классификации",
    "employee": "сотрудника",
    "acoin": "Acoin",
    "acoin transaction": "транзакции Acoin",
    "answer option": "варианта ответа",
    "employee groups": "групп сотрудника",
    "employee user permissions": "разрешений пользователя сотрудника",
    "employee achievement": "достижения сотрудника",
    "employee action log": "журнала действий сотрудника",
    "employee item": "предмета сотрудника",
    "employee log": "лога сотрудника",
    "employee medal": "медали сотрудника",
    "experience multiplier": "множителя опыта",
    "feedback": "обратной связи",
    "file path": "пути файла",
    "item": "предмета",
    "karma historу": "истории кармы",
    "karma settings": "настроек кармы",
    "level title": "названия уровня",
    "medal": "медали",
    "password policy": "политики паролей",
    "preloaded avatar": " загруженнего аватара",
    "request": "запроса",
    "shift history": "истории смен",
    "survey answer": "ответа на опрос",
    "survey question": "вопроса опроса",
    "system setting": "системной настройки",
    "test": "теста",
    "test attempt": "попытки теста",
    "test question": "вопроса теста",
    "theme": "темы",
    "theory": "теории",
    "usersession": "сессии пользователя",
    "test attempt question explanation": "объяснения вопроса попытки теста",
    "stat": "статистики",


}
ACTION_TRANSLATION = {
    "add": "добавление",
    "delete": "удаление",
    "change": "изменение",
    "view": "просмотр",
}


# Логика перевода с учетом падежей и множественных слов
def translate_permission_name(name):
    action_map = {
        "add": "Добавление",
        "change": "Изменение",
        "delete": "Удаление",
        "view": "Просмотр"
    }

    words = name.split(" ")
    action = action_map.get(words[1].lower(), words[1])

    model_name = " ".join(words[2:]).replace('_', ' ')

    # Ищем модель в словаре, начиная с самой длинной возможной комбинации
    translated_model_name = None
    for length in range(len(model_name.split()), 0, -1):
        model_key = " ".join(model_name.split()[:length])
        if model_key.lower() in MODEL_NAMES_TRANSLATION:
            translated_model_name = model_name.replace(model_key, MODEL_NAMES_TRANSLATION[model_key.lower()])
            break

    # Если не найдено ни одного соответствия, используем оригинальное имя модели
    if translated_model_name is None:
        translated_model_name = model_name

    return f"{action} {translated_model_name}"