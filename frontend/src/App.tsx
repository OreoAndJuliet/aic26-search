import { useState, useEffect } from 'react'
import './App.css'

interface SearchResult {
  video_id: string;
  frame_id: number;
  score: number;
  thumbnail_url: string;
  answer?: string;
}

function App() {
  const [queryType, setQueryType] = useState('KIS');
  const [textQuery, setTextQuery] = useState('');
  const [questionQuery, setQuestionQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSearch = async () => {
    setIsLoading(true);
    try {
      // Mock API call to our backend
      const response = await fetch('http://localhost:8000/api/v1/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query_type: queryType,
          text: textQuery,
          question: questionQuery,
          top_k: 50
        })
      });
      const data = await response.json();
      if (data.status === 'success') {
        setResults(data.data);
      }
    } catch (error) {
      console.error("Lỗi khi gọi API Backend:", error);
      alert("Chưa kết nối được Backend. Hãy đảm bảo uvicorn đang chạy ở port 8000.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app-container">
      <header className="header">
        <h1>AIC 2026 <span>Search Engine</span></h1>
        
        <div className="search-bar">
          <select 
            value={queryType} 
            onChange={(e) => setQueryType(e.target.value)}
            className="query-select"
          >
            <option value="KIS">Textual KIS</option>
            <option value="VQA">Q&A (VQA)</option>
            <option value="TRAKE">TRAKE</option>
          </select>
          
          <input 
            type="text" 
            placeholder={queryType === 'TRAKE' ? "Nhập chuỗi sự kiện (cách nhau bởi dấu phẩy)..." : "Nhập mô tả sự kiện..."}
            value={textQuery}
            onChange={(e) => setTextQuery(e.target.value)}
            className="search-input"
          />

          {queryType === 'VQA' && (
            <input 
              type="text" 
              placeholder="Nhập câu hỏi..."
              value={questionQuery}
              onChange={(e) => setQuestionQuery(e.target.value)}
              className="search-input question-input"
            />
          )}

          <button onClick={handleSearch} className="search-btn" disabled={isLoading}>
            {isLoading ? 'Đang tìm...' : 'Tìm Kiếm'}
          </button>
        </div>
      </header>

      <main className="main-content">
        <aside className="sidebar">
          <h2>Giỏ hàng (Đã chọn)</h2>
          <p className="empty-cart">Chưa chọn ảnh nào.</p>
          <button className="export-btn">Xuất Codabench ZIP</button>
        </aside>

        <section className="results-grid">
          {results.length === 0 && !isLoading && (
            <div className="no-results">Nhập mô tả để bắt đầu tìm kiếm.</div>
          )}
          {results.map((item, idx) => (
            <div key={idx} className="result-card">
              <div className="score-badge">R-Score: {item.score.toFixed(2)}</div>
              <img src={item.thumbnail_url} alt="thumbnail" loading="lazy" />
              <div className="card-info">
                <p><strong>Video:</strong> {item.video_id}</p>
                <p><strong>Frame:</strong> {item.frame_id}</p>
                {item.answer && <p className="answer"><strong>Đáp án:</strong> {item.answer}</p>}
                <button className="add-btn">Thêm vào giỏ</button>
              </div>
            </div>
          ))}
        </section>
      </main>
    </div>
  )
}

export default App
