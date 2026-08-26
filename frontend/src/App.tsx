import { useState, useEffect } from 'react'
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

interface PreviewItem {
  id: string;
  video_id: string;
  frame_id: string;
  img_url: string;
  is_missing: boolean;
  answer: string;
}

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App() {
  const [currentView, setCurrentView] = useState<'search' | 'preview'>('search');
  
  // Search View State
  const [queryType, setQueryType] = useState('KIS');
  const [textQuery, setTextQuery] = useState('');
  const [questionQuery, setQuestionQuery] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [cart, setCart] = useState<SearchResult[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [activeVideo, setActiveVideo] = useState<string | null>(null);
  const [isRebuilding, setIsRebuilding] = useState(false);
  const [queryId, setQueryId] = useState<number>(1);
  const [lastTrakeMeta, setLastTrakeMeta] = useState<any>(null);

  // Preview View State
  const [previewFiles, setPreviewFiles] = useState<string[]>([]);
  const [selectedPreviewFile, setSelectedPreviewFile] = useState<string>('');
  const [previewData, setPreviewData] = useState<{type: string, items: PreviewItem[]}>({ type: '', items: [] });
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);

  useEffect(() => {
    if (currentView === 'preview' && previewFiles.length === 0) {
      fetchPreviewFiles();
    }
  }, [currentView]);

  const fetchPreviewFiles = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/preview`);
      const data = await res.json();
      if (data.status === 'success') {
        setPreviewFiles(data.files);
        if (data.files.length > 0) {
          handleSelectPreviewFile(data.files[0]);
        }
      }
    } catch (e) {
      console.error("Failed to load preview files", e);
    }
  };

  const handleSelectPreviewFile = async (filename: string) => {
    setSelectedPreviewFile(filename);
    setIsPreviewLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/preview/${filename}`);
      const data = await res.json();
      if (data.status === 'success') {
        setPreviewData({ type: data.type, items: data.items });
      }
    } catch (e) {
      console.error("Failed to load preview data", e);
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleRebuildIndex = async () => {
    if (!window.confirm("Are you sure you want to rebuild the FAISS index from .npy features? This may take some time depending on data size.")) return;
    setIsRebuilding(true);
    try {
      const response = await fetch(`${API_BASE}/api/system/rebuild-index`, {
        method: 'POST'
      });
      const data = await response.json();
      if (data.status === 'success') {
        alert(data.message);
      } else {
        alert("Failed to trigger index rebuild.");
      }
    } catch {
      alert("Cannot connect to Backend. Make sure uvicorn is running on port 8000.");
    } finally {
      setIsRebuilding(false);
    }
  };

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    setIsLoading(true);
    try {
      const payload: any = {
        query_type: queryType,
        text: textQuery,
        question: questionQuery,
        top_k: 100
      };

      if (queryType === 'TRAKE') {
        payload.events = textQuery.split(',').map(s => s.trim()).filter(s => s);
      }

      const response = await fetch(`${API_BASE}/api/v1/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (data.status === 'success') {
        setResults(data.data);
        setLastTrakeMeta(data.trake || null);
      }
    } catch {
      alert("Cannot connect to Backend. Make sure uvicorn is running on port 8000.");
    } finally {
      setIsLoading(false);
    }
  };

  const isInCart = (item: SearchResult) => 
    !!cart.find(c => c.video_id === item.video_id && c.frame_id === item.frame_id);

  const addToCart = (item: SearchResult) => {
    if (!isInCart(item)) {
      setCart(prev => [...prev, item]);
    }
  };

  const removeFromCart = (index: number) => {
    setCart(prev => prev.filter((_, i) => i !== index));
  };

  const exportToCodabench = async () => {
    if (cart.length === 0) return;
    
    try {
      const payload = {
        task_type: queryType,
        results: cart.map(item => ({
          video_id: item.video_id,
          frame_id: item.frame_id,
          answer: item.answer || ""
        })),
        trake_meta: lastTrakeMeta,
        query_id: queryId
      };

      const res = await fetch(`${API_BASE}/api/export/submission`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const data = await res.json();
      if (data.status === 'SUCCESS' && data.zip_download_url) {
        window.location.href = `${API_BASE}${data.zip_download_url}`;
      } else {
        alert("Export failed: " + (data.validation_errors?.join(", ") || "Unknown error"));
      }
    } catch (err) {
      alert("Failed to export submission. Check backend logs.");
    }
  };

  return (
    <div className="app-container">
      {/* ── HEADER ── */}
      <header className="header">
        <div className="brand">
          <div className="logo-icon">O</div>
          <h1>Oreo<span>AndJuliet</span></h1>
        </div>

        <div className="view-switcher" style={{ display: 'flex', gap: '10px', marginLeft: '30px' }}>
          <button 
            className={`view-btn ${currentView === 'search' ? 'active' : ''}`}
            onClick={() => setCurrentView('search')}
          >
            Search Engine
          </button>
          <button 
            className={`view-btn ${currentView === 'preview' ? 'active' : ''}`}
            onClick={() => setCurrentView('preview')}
          >
            Submissions Preview
          </button>
        </div>

        {currentView === 'search' && (
          <form className="search-wrapper" onSubmit={handleSearch} style={{ marginLeft: 'auto' }}>
            <select value={queryType} onChange={e => setQueryType(e.target.value)} className="query-select">
              <option value="KIS">Text KIS</option>
              <option value="VQA">Visual QA</option>
              <option value="TRAKE">TRAKE</option>
            </select>

            <div className="search-inputs">
              <input
                type="text"
                placeholder={queryType === 'TRAKE' ? "Enter event sequence, comma separated..." : "Describe the scene you're looking for..."}
                value={textQuery}
                onChange={e => setTextQuery(e.target.value)}
                className="search-input"
              />
              {queryType === 'VQA' && (
                <input
                  type="text"
                  placeholder="Enter your question..."
                  value={questionQuery}
                  onChange={e => setQuestionQuery(e.target.value)}
                  className="search-input question-input"
                />
              )}
            </div>

            <button type="submit" className="search-btn" disabled={isLoading}>
              {isLoading ? 'Searching...' : 'Search'}
            </button>
          </form>
        )}

        <div className="header-stats" style={{ marginLeft: currentView === 'preview' ? 'auto' : '15px' }}>
          {currentView === 'search' && (
            <>
              <button 
                type="button"
                className="redo-vector-btn" 
                onClick={handleRebuildIndex}
                disabled={isRebuilding}
                style={{ marginRight: '15px', padding: '6px 12px', background: '#e74c3c', color: 'white', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 600, fontSize: '13px' }}
              >
                {isRebuilding ? 'Rebuilding...' : 'Redo Vector'}
              </button>
              <div className="stat-pill">
                <div className="stat-dot"></div>
                <span>Results: </span>
                <span className="stat-value">{results.length}</span>
              </div>
              <div className="stat-pill">
                <span>Selected: </span>
                <span className="stat-value">{cart.length}</span>
              </div>
            </>
          )}
        </div>
      </header>

      {/* ── MAIN CONTENT ── */}
      <main className="main-content">
        {currentView === 'search' ? (
          <>
            <section className="results-area">
              {results.length > 0 && (
                <div className="results-header">
                  <h2>Showing <strong>{results.length}</strong> results for "{textQuery || 'all'}"</h2>
                </div>
              )}

              <div className="results-grid">
                {isLoading && (
                  <div className="loading-container">
                    <div className="spinner"></div>
                    <p>Searching across video frames...</p>
                  </div>
                )}

                {results.length === 0 && !isLoading && (
                  <div className="empty-state">
                    <div className="empty-state-icon">🔍</div>
                    <h3>Ready to explore</h3>
                    <p>Describe a scene, event, or object to search through thousands of video frames instantly.</p>
                  </div>
                )}

                {results.map((item, idx) => (
                  <div key={`${item.video_id}-${item.frame_id}`} className="result-card">
                    <div className={`rank-badge ${idx < 3 ? 'top-3' : ''}`}>{idx + 1}</div>
                    <div className="score-badge">{item.score.toFixed(2)}</div>

                    <div className="image-container" onClick={() => setActiveVideo(`${API_BASE}/static/videos/${item.video_id}.mp4`)}>
                      <img src={item.thumbnail_url} alt={`Frame ${item.frame_id} from ${item.video_id}`} loading="lazy" />
                      <div className="play-overlay">
                        <div className="play-btn">
                          <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                        </div>
                      </div>
                    </div>

                    <div className="card-body">
                      <div className="meta-row">
                        <span className="meta-chip"><strong>{item.video_id}</strong></span>
                        <span className="meta-chip">F: <strong>{item.frame_id}</strong></span>
                      </div>

                      {item.answer && (
                        <div className="answer-box">
                          <label>AI Answer</label>
                          <input
                            type="text"
                            defaultValue={item.answer}
                            onChange={e => { item.answer = e.target.value; }}
                            className="edit-answer"
                          />
                        </div>
                      )}

                      <button
                        onClick={() => addToCart(item)}
                        className={`add-btn ${isInCart(item) ? 'added' : ''}`}
                        disabled={isInCart(item)}
                      >
                        {isInCart(item) ? (
                          <>
                            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.5" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7"/></svg>
                            Added
                          </>
                        ) : (
                          <>
                            <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4"/></svg>
                            Add to selection
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </section>

            {/* ── SIDEBAR ── */}
            <aside className="sidebar">
              <div className="sidebar-header">
                <h2>
                  Selection
                  <span className={`cart-badge ${cart.length === 0 ? 'empty' : ''}`}>{cart.length}</span>
                </h2>
                <p className="sidebar-subtitle">Items ready for submission</p>
              </div>

              <div className="cart-items">
                {cart.length === 0 ? (
                  <div className="empty-cart">
                    <div className="empty-cart-icon">📦</div>
                    <p>No items selected yet. Click "Add to selection" on any result card.</p>
                  </div>
                ) : (
                  cart.map((item, idx) => (
                    <div key={`cart-${item.video_id}-${item.frame_id}`} className="cart-item">
                      <img src={item.thumbnail_url} alt="thumb" />
                      <div className="cart-item-info">
                        <p className="vid-id">{item.video_id}</p>
                        <p className="frm-id">Frame {item.frame_id}</p>
                      </div>
                      <button onClick={() => removeFromCart(idx)} className="remove-btn" title="Remove">✕</button>
                    </div>
                  ))
                )}
              </div>

              <div className="sidebar-footer">
                <div className="query-id-input">
                  <label>Query ID:</label>
                  <input 
                    type="number" 
                    min="1" 
                    value={queryId} 
                    onChange={e => setQueryId(parseInt(e.target.value) || 1)} 
                  />
                </div>
                <button onClick={exportToCodabench} className="export-btn" disabled={cart.length === 0}>
                  <svg width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                  Export ZIP for Codabench
                </button>
              </div>
            </aside>
          </>
        ) : (
          <section className="preview-area" style={{ width: '100%', display: 'flex', flexDirection: 'column' }}>
            <div className="preview-controls" style={{ padding: '20px', background: 'white', borderBottom: '1px solid #eee', display: 'flex', alignItems: 'center', gap: '15px' }}>
              <h2 style={{ margin: 0 }}>Review Submission</h2>
              <select 
                value={selectedPreviewFile} 
                onChange={e => handleSelectPreviewFile(e.target.value)}
                style={{ padding: '8px 12px', borderRadius: '4px', border: '1px solid #ccc', minWidth: '300px' }}
              >
                {previewFiles.map(f => <option key={f} value={f}>{f}</option>)}
              </select>
              {previewData.type && (
                <span style={{ padding: '4px 8px', background: '#e0f2fe', color: '#0284c7', borderRadius: '4px', fontWeight: 'bold' }}>
                  {previewData.type.toUpperCase()} Task
                </span>
              )}
              <span style={{ color: '#666', marginLeft: 'auto' }}>
                {previewData.items.length} items
              </span>
            </div>

            <div className="results-grid" style={{ padding: '20px' }}>
              {isPreviewLoading && (
                <div className="loading-container" style={{ width: '100%', gridColumn: '1 / -1' }}>
                  <div className="spinner"></div>
                  <p>Loading preview...</p>
                </div>
              )}
              
              {!isPreviewLoading && previewData.items.map((item, idx) => (
                <div key={item.id} className="result-card">
                  <div className="rank-badge">{idx + 1}</div>
                  
                  <div className="image-container" onClick={() => setActiveVideo(`${API_BASE}/static/videos/${item.video_id}.mp4`)}>
                    {item.is_missing ? (
                      <div style={{ height: '180px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#fee2e2', color: '#ef4444', fontWeight: 'bold' }}>
                        Image Not Found
                      </div>
                    ) : (
                      <img src={`${API_BASE}${item.img_url}`} alt={`Frame ${item.frame_id}`} loading="lazy" />
                    )}
                    <div className="play-overlay">
                      <div className="play-btn">
                        <svg viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
                      </div>
                    </div>
                  </div>

                  <div className="card-body">
                    <div className="meta-row">
                      <span className="meta-chip"><strong>{item.video_id}</strong></span>
                      <span className="meta-chip">F: <strong>{item.frame_id}</strong></span>
                    </div>

                    {item.answer && (
                      <div className="qa-answer" style={{ marginTop: '10px', padding: '8px', background: '#ecfdf5', color: '#059669', borderRadius: '4px', fontWeight: 'bold', textAlign: 'center', wordBreak: 'break-word' }}>
                        {item.answer}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>

      {/* ── VIDEO MODAL ── */}
      {activeVideo && (
        <div className="modal-overlay" onClick={() => setActiveVideo(null)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Video Preview</h3>
              <button className="close-modal" onClick={() => setActiveVideo(null)}>✕</button>
            </div>
            <div className="video-container">
              <video controls autoPlay style={{ width: '100%', borderRadius: '12px', background: '#000' }}>
                <source src={activeVideo} type="video/mp4" />
                Your browser does not support the video tag.
              </video>
              <span className="video-url-badge" style={{ marginTop: '10px', display: 'inline-block' }}>{activeVideo}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default App
