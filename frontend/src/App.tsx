import { useState } from 'react'
import JSZip from 'jszip'
import { saveAs } from 'file-saver'
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
  const [cart, setCart] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  
  // Video Modal State
  const [activeVideo, setActiveVideo] = useState<string | null>(null);

  const handleSearch = async () => {
    setIsLoading(true);
    try {
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

  const addToCart = (item: SearchResult) => {
    // Avoid duplicates
    if (!cart.find(c => c.video_id === item.video_id && c.frame_id === item.frame_id)) {
      setCart([...cart, item]);
    }
  };

  const removeFromCart = (index: number) => {
    const newCart = [...cart];
    newCart.splice(index, 1);
    setCart(newCart);
  };

  const exportToCodabench = async () => {
    if (cart.length === 0) {
      alert("Giỏ hàng trống!");
      return;
    }

    const zip = new JSZip();
    
    // Format: <video_id>, <frame_id>
    // For VQA: <video_id>, <frame_id>, "<answer>"
    
    // Group by query conceptually (here we assume all in cart belong to the current query for simplicity)
    // In a real scenario, you might have multiple queries. For now, we put them all in 1 csv file.
    
    let csvContent = "";
    cart.forEach(item => {
      if (item.answer) {
        // Escape quotes just in case
        const safeAnswer = item.answer.replace(/"/g, '""');
        csvContent += `${item.video_id},${item.frame_id},"${safeAnswer}"\n`;
      } else {
        csvContent += `${item.video_id},${item.frame_id}\n`;
      }
    });

    zip.file("query-results.csv", csvContent);
    
    const content = await zip.generateAsync({ type: "blob" });
    saveAs(content, "submission.zip");
  };

  const playVideo = (videoId: string) => {
    // URL to the static video hosted on backend
    setActiveVideo(`http://localhost:8000/static/videos/${videoId}.mp4`);
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
          <h2>Giỏ hàng ({cart.length})</h2>
          
          <div className="cart-items">
            {cart.length === 0 ? (
              <p className="empty-cart">Chưa chọn ảnh nào.</p>
            ) : (
              cart.map((item, idx) => (
                <div key={idx} className="cart-item">
                  <img src={item.thumbnail_url} alt="cart thumb" />
                  <div className="cart-item-info">
                    <p>{item.video_id}</p>
                    <p>Frame: {item.frame_id}</p>
                  </div>
                  <button onClick={() => removeFromCart(idx)} className="remove-btn">✕</button>
                </div>
              ))
            )}
          </div>

          <button onClick={exportToCodabench} className="export-btn" disabled={cart.length === 0}>
            Xuất Codabench ZIP
          </button>
        </aside>

        <section className="results-grid">
          {results.length === 0 && !isLoading && (
            <div className="no-results">Nhập mô tả để bắt đầu tìm kiếm.</div>
          )}
          {results.map((item, idx) => (
            <div key={idx} className="result-card">
              <div className="score-badge">R-Score: {item.score.toFixed(2)}</div>
              
              <div className="image-container" onClick={() => playVideo(item.video_id)}>
                <img src={item.thumbnail_url} alt="thumbnail" loading="lazy" />
                <div className="play-overlay">▶</div>
              </div>

              <div className="card-info">
                <p><strong>Video:</strong> {item.video_id}</p>
                <p><strong>Frame:</strong> {item.frame_id}</p>
                {item.answer && (
                  <p className="answer">
                    <strong>Đáp án:</strong> 
                    <input 
                      type="text" 
                      defaultValue={item.answer} 
                      onChange={(e) => {
                        // Cập nhật lại answer trước khi add vào giỏ (nếu user sửa)
                        item.answer = e.target.value;
                      }}
                      className="edit-answer"
                    />
                  </p>
                )}
                <button onClick={() => addToCart(item)} className="add-btn">Thêm vào giỏ</button>
              </div>
            </div>
          ))}
        </section>
      </main>

      {/* Video Player Modal */}
      {activeVideo && (
        <div className="modal-overlay" onClick={() => setActiveVideo(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <button className="close-modal" onClick={() => setActiveVideo(null)}>✕</button>
            <h3>Video Preview</h3>
            {/* Using a placeholder for video since we don't have real mp4 yet */}
            <div className="video-placeholder">
              <p>Mô phỏng phát Video từ Backend</p>
              <p className="video-url">{activeVideo}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
