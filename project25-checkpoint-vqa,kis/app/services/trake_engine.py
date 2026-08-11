class TRAKEEngine:
    def align(self, english_text: str, top_k: int = 50):
        """DTW Alignment cho chuỗi sự kiện theo thời gian"""
        from app.services.kis_engine import kis_engine
        return kis_engine.search(english_text, top_k)

trake_engine = TRAKEEngine()
