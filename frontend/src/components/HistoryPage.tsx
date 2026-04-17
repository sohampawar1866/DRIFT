import { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';
import { Download, Trash2 } from 'lucide-react';

export const HistoryPage = () => {
    const [history, setHistory] = useState<any[]>([]);
    const [isClearing, setIsClearing] = useState(false);
    const navigate = useNavigate();

    useEffect(() => {
        axios.get('http://localhost:8000/api/v1/tracker/search')
            .then(res => setHistory(res.data))
            .catch(console.error);
    }, []);

    const handleRevisit = async (id: string) => {
        await axios.post(`http://localhost:8000/api/v1/tracker/revisit/${id}`);
        navigate('/drift', { state: { highlightedId: id } });
    };

    const handleClearHistory = async () => {
        if (history.length === 0 || isClearing) return;

        const shouldClear = window.confirm('Clear all deployment history records? This cannot be undone.');
        if (!shouldClear) return;

        setIsClearing(true);
        try {
            await axios.delete('http://localhost:8000/api/v1/tracker/search');
            setHistory([]);
        } catch (error) {
            console.error(error);
            window.alert('Failed to clear history. Please try again.');
        } finally {
            setIsClearing(false);
        }
    };

    const handleExportHistory = () => {
        if (history.length === 0) {
            window.alert('No history records available to export.');
            return;
        }

        const payload = {
            exportedAt: new Date().toISOString(),
            totalRecords: history.length,
            records: history,
        };

        const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `drift-history-${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    };

    return (
        <div style={{ padding: '40px', background: '#1e2229', minHeight: '100vh', color: '#e2e8f0', boxSizing: 'border-box', fontFamily: 'Inter, sans-serif' }}>
            <h2 style={{ color: '#f59e0b', marginBottom: '1.5rem', fontWeight: 'bold' }}>Sector Deployment History</h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '10px', marginBottom: '30px' }}>
                <button
                    onClick={() => navigate('/drift')}
                    style={{ background: '#272c35', color: '#e2e8f0', border: '1px solid #38404d', padding: '10px 20px', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 1px 2px rgba(0,0,0,0.2)' }}
                >
                    &larr; Return to Dashboard
                </button>

                <button
                    onClick={() => navigate('/drift/dashboard')}
                    style={{ background: '#1f7a5d', color: '#eaf8f3', border: '1px solid #279a74', padding: '10px 20px', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 1px 2px rgba(0,0,0,0.2)' }}
                >
                    Open Intel Dashboard
                </button>

                <button
                    onClick={handleExportHistory}
                    style={{ background: '#2b3442', color: '#e2e8f0', border: '1px solid #425064', padding: '10px 16px', borderRadius: '4px', cursor: 'pointer', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.2)' }}
                >
                    <Download size={16} />
                    Export History
                </button>

                <button
                    onClick={handleClearHistory}
                    disabled={history.length === 0 || isClearing}
                    style={{ background: history.length === 0 || isClearing ? '#3a3f48' : '#7f1d1d', color: history.length === 0 || isClearing ? '#9ca3af' : '#fee2e2', border: history.length === 0 || isClearing ? '1px solid #4b5563' : '1px solid #b91c1c', padding: '10px 16px', borderRadius: '4px', cursor: history.length === 0 || isClearing ? 'not-allowed' : 'pointer', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '8px', boxShadow: '0 1px 2px rgba(0,0,0,0.2)' }}
                >
                    <Trash2 size={16} />
                    {isClearing ? 'Clearing...' : 'Clear History'}
                </button>
            </div>

            <div style={{ display: 'grid', gap: '15px', maxWidth: '800px' }}>
                {history.slice().reverse().map((item: any) => (
                    <div key={item.id} style={{ border: '1px solid #38404d', padding: '20px', borderRadius: '8px', background: '#272c35', display: 'flex', justifyContent: 'space-between', alignItems: 'center', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.2)' }}>
                        <div>
                            <h3 style={{ margin: '0 0 10px 0', color: '#e2e8f0', fontWeight: 'bold' }}>{item.id}</h3>
                            <div style={{ color: '#94a3b8', fontSize: '14px', lineHeight: '1.5' }}>
                                <strong style={{ color: '#cbd5e1' }}>Logged:</strong> {item.date} <br />
                                <strong style={{ color: '#cbd5e1' }}>Density Profile:</strong> {(item.density * 100).toFixed(1)}%<br />
                                <strong style={{ color: '#cbd5e1' }}>Coordinates:</strong> {item.center[1].toFixed(4)}&deg;N, {item.center[0].toFixed(4)}&deg;E
                            </div>
                        </div>
                        <button
                            onClick={() => handleRevisit(item.id)}
                            style={{ padding: '12px 24px', background: '#10b981', color: '#1e2229', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold', boxShadow: '0 2px 4px rgba(16, 185, 129, 0.2)' }}
                        >
                            REVISIT ON MAP
                        </button>
                    </div>
                ))}
                {history.length === 0 && (
                    <div style={{ color: '#94a3b8' }}>No tracking sectors deployed yet.</div>
                )}
            </div>
        </div>
    );
};
