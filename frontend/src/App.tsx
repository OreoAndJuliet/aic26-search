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

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
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
    if (cart.length === 0) return;
    const zip = new JSZip();
    let csvContent = "";
    cart.forEach(item => {
      if (item.answer) {
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
    setActiveVideo(`http://localhost:8000/static/videos/${videoId}.mp4`);
  };

  return (
    <div className="app-container">
      {/* HEADER */}
      <header className="header">
        <div className="brand">
          <h1>AIC 2026 <span>Nexus</span></h1>
        </div>
        
        <form className="search-wrapper" onSubmit={handleSearch}>
          <select 
            value={queryType} 
            onChange={(e) => setQueryType(e.target.value)}
            className="query-select"
          >
            <option value="KIS">Text KIS</option>
            <option value="VQA">Visual Q&A</option>
            <option value="TRAKE">TRAKE</option>
          </select>
          
          <div className="search-inputs">
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
                placeholder="Nhập câu hỏi VQA..."
                value={questionQuery}
                onChange={(e) => setQuestionQuery(e.target.value)}
                className="search-input question-input"
              />
            )}
          </div>

          <button type="submit" className="search-btn" disabled={isLoading}>
            {isLoading ? 'Đang tìm...' : 'Khám phá'}
          </button>
        </form>
      </header>

      {/* MAIN LAYOUT */}
      <main className="main-content">
        
        {/* RESULTS AREA */}
        <section className="results-area">
          <div className="results-grid">
            {results.length === 0 && !isLoading && (
              <div className="no-results">Vũ trụ dữ liệu đang chờ bạn khám phá. Nhập mô tả để bắt đầu.</div>
            )}
            
            {results.map((item, idx) => (
              <div key={idx} className="result-card">
                <div className="score-badge">Score <span>{item.score.toFixed(2)}</span></div>
                
                <div className="image-container" onClick={() => playVideo(item.video_id)}>
                  <img src={item.thumbnail_url} alt="thumbnail" loading="lazy" />
                  <div className="play-overlay">
                    {/* SVG Play Icon */}
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path d="M8 5v14l11-7z" />
                    </svg>
                  </div>
                </div>

                <div className="card-info">
                  <div className="meta-row">
                    <span className="meta-tag">Video: <strong>{item.video_id}</strong></span>
                    <span className="meta-tag">Frame: <strong>{item.frame_id}</strong></span>
                  </div>
                  
                  {item.answer && (
                    <div className="answer-box">
                      <label>AI Answer (Có thể sửa):</label>
                      <input 
                        type="text" 
                        defaultValue={item.answer} 
                        onChange={(e) => { item.answer = e.target.value; }}
                        className="edit-answer"
                      />
                    </div>
                  )}
                  
                  <button onClick={() => addToCart(item)} className="add-btn">
                    <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4"></path>
                    </svg>
                    Đưa vào giỏ
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* SIDEBAR CART */}
        <aside className="sidebar">
          <h2>Giỏ lựa chọn <span className="cart-count">{cart.length}</span></h2>
          
          <div className="cart-items">
            {cart.length === 0 ? (
              <p className="empty-cart">Chưa có dữ liệu nào được chọn.</p>
            ) : (
              cart.map((item, idx) => (
                <div key={idx} className="cart-item">
                  <img src={item.thumbnail_url} alt="cart thumb" />
                  <div className="cart-item-info">
                    <p className="vid-id">{item.video_id}</p>
                    <p className="frm-id">Frame: {item.frame_id}</p>
                  </div>
                  <button onClick={() => removeFromCart(idx)} className="remove-btn">
                    ✕
                  </button>
                </div>
              ))
            )}
          </div>

          <button 
            onClick={exportToCodabench} 
            className="export-btn" 
            disabled={cart.length === 0}
          >
            Xuất ZIP Codabench
          </button>
        </aside>
      </main>

      {/* VIDEO MODAL */}
      {activeVideo && (
        <div className="modal-overlay" onClick={() => setActiveVideo(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Preview Video</h3>
              <button className="close-modal" onClick={() => setActiveVideo(null)}>✕</button>
            </div>
            
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
