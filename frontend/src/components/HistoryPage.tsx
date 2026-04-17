import React, { useEffect, useState } from 'react';
import axios from 'axios';
import { useNavigate } from 'react-router-dom';

export const HistoryPage = () => {
    const [history, setHistory] = useState<any[]>([]);
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

    return (
        <div style={{ padding: '40px', background: '#0a0e17', minHeight: '100vh', color: '#fff', boxSizing: 'border-box', fontFamily: 'Inter, sans-serif' }}>
            <h2 style={{ color: '#00e5ff' }}>Sector Deployment History</h2>
            <button 
                onClick={() => navigate('/drift')} 
                style={{ background: '#1f2937', color: '#fff', border: '1px solid #374151', padding: '10px 20px', borderRadius: '4px', cursor: 'pointer', marginBottom: '30px' }}
            >
                &larr; Return to Dashboard
            </button>

            <div style={{ display: 'grid', gap: '15px', maxWidth: '800px' }}>
                {history.slice().reverse().map((item: any) => (
                    <div key={item.id} style={{ border: '1px solid #1f2937', padding: '20px', borderRadius: '8px', background: '#111827', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div>
                            <h3 style={{ margin: '0 0 10px 0', color: '#fff' }}>{item.id}</h3>
                            <div style={{ color: '#9ca3af', fontSize: '14px', lineHeight: '1.5' }}>
                                <strong>Logged:</strong> {item.date} <br />
                                <strong>Density Profile:</strong> {(item.density * 100).toFixed(1)}%<br />
                                <strong>Coordinates:</strong> {item.center[1].toFixed(4)}&deg;N, {item.center[0].toFixed(4)}&deg;E
                            </div>
                        </div>
                        <button 
                            onClick={() => handleRevisit(item.id)}
                            style={{ padding: '12px 24px', background: '#00e5ff', color: '#000', border: 'none', borderRadius: '4px', cursor: 'pointer', fontWeight: 'bold' }}
                        >
                            REVISIT ON MAP
                        </button>
                    </div>
                ))}
                {history.length === 0 && (
                    <div style={{ color: '#9ca3af' }}>No tracking sectors deployed yet.</div>
                )}
            </div>
        </div>
    );
};
