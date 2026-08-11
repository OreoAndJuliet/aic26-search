import requests


class TranslatorService:
    def translate(self, text: str) -> str:
        """Dịch truy vấn từ Tiếng Việt sang Tiếng Anh"""
        if not text:
            return ""
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=vi&tl=en&dt=t&q={text}"
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                result = response.json()
                translated = "".join([item[0] for item in result[0] if item[0]])
                return translated
        except (requests.RequestException, ValueError) as e:
            print(f"⚠️ Lỗi dịch thuật: {e}, chuyển sang dùng văn bản gốc.")
        return text

translator = TranslatorService()
