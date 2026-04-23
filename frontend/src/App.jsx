import { useState, useEffect } from "react"

export default function App() {
    const [input, setInput] = useState("")
    const [response, setResponse] = useState("")
    const [loading, setLoading] = useState(false)
    const [sessionId, setSessionId] = useState("")

    useEffect(() => {
        // Generate a simple unique session ID for the current session
        setSessionId(`session_${Math.random().toString(36).substring(2, 11)}`)
    }, [])

    const handleSubmit = async () => {
        if (!input.trim()) return

        setLoading(true)
        setResponse("")

        try {
            const res = await fetch("http://localhost:8000/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": "Bearer your-secret-token"
                },
                body: JSON.stringify({
                    message: input,
                    user_id: "ui_user",
                    session_id: sessionId
                })
            })

            const data = await res.json()
            setResponse(data.response)
        } catch (err) {
            setResponse("Error calling API")
        } finally {
            setLoading(false)
        }
    }

    return (
        <div style={{ 
            maxWidth: "800px", 
            margin: "40px auto", 
            padding: "30px", 
            fontFamily: "'Outfit', 'Inter', sans-serif",
            backgroundColor: "#f8fafc",
            borderRadius: "16px",
            boxShadow: "0 10px 25px rgba(0,0,0,0.05)"
        }}>
            <h2 style={{ color: "#1e293b", marginBottom: "24px" }}>GulliverTravels Chat</h2>

            <div style={{ display: "flex", gap: "12px", marginBottom: "30px" }}>
                <input
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                    placeholder="Ask Gulliver about your travels..."
                    style={{ 
                        flex: 1, 
                        padding: "14px 18px", 
                        borderRadius: "12px", 
                        border: "1px solid #e2e8f0",
                        fontSize: "16px",
                        outline: "none",
                        transition: "border-color 0.2s",
                        boxShadow: "inset 0 2px 4px rgba(0,0,0,0.02)"
                    }}
                />

                <button 
                    onClick={handleSubmit} 
                    disabled={loading}
                    style={{ 
                        padding: "0 24px", 
                        backgroundColor: "#3b82f6", 
                        color: "white", 
                        border: "none", 
                        borderRadius: "12px", 
                        fontWeight: "600",
                        cursor: loading ? "not-allowed" : "pointer",
                        transition: "background-color 0.2s",
                        opacity: loading ? 0.7 : 1
                    }}
                >
                    {loading ? "Thinking..." : "Send"}
                </button>
            </div>

            <div style={{ 
                backgroundColor: "white", 
                padding: "24px", 
                borderRadius: "12px", 
                border: "1px solid #e2e8f0",
                minHeight: "200px"
            }}>
                <h4 style={{ color: "#64748b", marginTop: 0, marginBottom: "16px", fontSize: "14px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                    Assistant Response
                </h4>

                {loading ? (
                    <div style={{ display: "flex", gap: "4px" }}>
                        <div className="dot" style={{ width: "8px", height: "8px", backgroundColor: "#3b82f6", borderRadius: "50%", animation: "pulse 1s infinite" }}></div>
                        <div className="dot" style={{ width: "8px", height: "8px", backgroundColor: "#3b82f6", borderRadius: "50%", animation: "pulse 1s infinite 0.2s" }}></div>
                        <div className="dot" style={{ width: "8px", height: "8px", backgroundColor: "#3b82f6", borderRadius: "50%", animation: "pulse 1s infinite 0.4s" }}></div>
                    </div>
                ) : (
                    <div style={{ 
                        whiteSpace: "pre-wrap", 
                        color: "#334155", 
                        lineHeight: "1.6",
                        fontSize: "16px"
                    }}>
                        {response || "Ready to help you plan your next adventure."}
                    </div>
                )}
            </div>
            
            <style>{`
                @keyframes pulse {
                    0%, 100% { transform: scale(1); opacity: 1; }
                    50% { transform: scale(1.2); opacity: 0.5; }
                }
            `}</style>
        </div>
    )
}