class Notifier:
    def __init__(self, token=None):
        self.token = token

    def send(self, message):
        # Здесь будет логика отправки уведомлений (например, в Telegram)
        print(f"[NOTIFY] {message}") 