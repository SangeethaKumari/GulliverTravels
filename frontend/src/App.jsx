import { useState, useEffect } from "react"

export default function App() {
    const [input, setInput] = useState("")
    const [response, setResponse] = useState("")
    const [loading, setLoading] = useState(false)
    const [chatSessionId, setChatSessionId] = useState("")
    const [monitorSessionId, setMonitorSessionId] = useState("")
    const [monitorState, setMonitorState] = useState(null)
    const [flightDetails, setFlightDetails] = useState(null)

    useEffect(() => {
        // Generate a simple unique session ID for the chat session
        setChatSessionId(`session_${Math.random().toString(36).substring(2, 11)}`)
    }, [])

    // Poll the monitor status endpoint if monitorSessionId is set
    useEffect(() => {
        if (!monitorSessionId) return

        let isMounted = true
        const pollStatus = async () => {
            try {
                const res = await fetch(`http://localhost:8000/api/monitor/status?session_id=${monitorSessionId}`, {
                    headers: {
                        "Authorization": "Bearer your-secret-token"
                    }
                })
                const data = await res.json()
                if (isMounted && data.status === "success") {
                    setMonitorState(data.state)
                }
            } catch (err) {
                console.error("Error polling status:", err)
            }
        }

        // Run immediately, then every 3 seconds
        pollStatus()
        const interval = setInterval(pollStatus, 3000)

        return () => {
            isMounted = false
            clearInterval(interval)
        }
    }, [monitorSessionId])

    const handleSubmit = async () => {
        if (!input.trim()) return

        setLoading(true)
        setResponse("")

        // If they enter a new track/monitor command, reset the previous status board
        const isMonitorCmd = input.toLowerCase().includes("monitor") || input.toLowerCase().includes("track")
        if (isMonitorCmd) {
            setMonitorState(null)
            setMonitorSessionId("")
            setFlightDetails(null)
        }

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
                    session_id: chatSessionId
                })
            })

            const data = await res.json()
            setResponse(data.response)

            // If the response returns structured monitoring metadata
            if (data.session_id) {
                setMonitorSessionId(data.session_id)
                setFlightDetails({
                    airlineCode: data.airline_code,
                    flightNumber: data.flight_number,
                    arrivalTime: data.arrival_time,
                    initialStatus: data.status
                })
            }
        } catch (err) {
            setResponse("Error calling API")
        } finally {
            setLoading(false)
        }
    }

    return (
        <div style={{ 
            maxWidth: "950px", 
            margin: "40px auto", 
            padding: "40px 30px", 
            fontFamily: "'Outfit', 'Inter', sans-serif",
            backgroundColor: "#0f172a",
            color: "#e2e8f0",
            borderRadius: "24px",
            boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.5)",
            border: "1px solid #1e293b"
        }}>
            {/* Header */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "32px" }}>
                <div>
                    <h2 style={{ margin: 0, fontSize: "28px", fontWeight: "700", background: "linear-gradient(to right, #60a5fa, #3b82f6)", WebkitBackgroundClip: "text", WebkitTextFillColor: "transparent" }}>
                        GulliverTravels
                    </h2>
                    <p style={{ margin: "4px 0 0 0", color: "#94a3b8", fontSize: "14px" }}>Intelligent Multi-Agent Travel Orchestrator</p>
                </div>
                <div style={{ display: "flex", gap: "8px", alignItems: "center" }}>
                    <div style={{ width: "8px", height: "8px", borderRadius: "50%", backgroundColor: "#10b981", boxShadow: "0 0 8px #10b981" }} />
                    <span style={{ fontSize: "12px", color: "#64748b", fontWeight: "600", textTransform: "uppercase" }}>System Active</span>
                </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: monitorSessionId ? "1.2fr 1fr" : "1fr", gap: "30px" }}>
                {/* Left Side: Chat Console */}
                <div style={{ display: "flex", flexDirection: "column", gap: "20px" }}>
                    <div style={{ display: "flex", gap: "12px" }}>
                        <input
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
                            placeholder="Type: monitor F9 2486 on 2026-05-30"
                            style={{ 
                                flex: 1, 
                                padding: "16px 20px", 
                                borderRadius: "16px", 
                                border: "1px solid #334155",
                                backgroundColor: "#1e293b",
                                color: "white",
                                fontSize: "16px",
                                outline: "none",
                                transition: "border-color 0.2s",
                                boxShadow: "inset 0 2px 4px rgba(0,0,0,0.1)"
                            }}
                        />

                        <button 
                            onClick={handleSubmit} 
                            disabled={loading}
                            style={{ 
                                padding: "0 28px", 
                                backgroundColor: "#3b82f6", 
                                color: "white", 
                                border: "none", 
                                borderRadius: "16px", 
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
                        backgroundColor: "#1e293b", 
                        padding: "28px", 
                        borderRadius: "20px", 
                        border: "1px solid #334155",
                        minHeight: "220px",
                        boxShadow: "0 4px 6px -1px rgba(0, 0, 0, 0.1)"
                    }}>
                        <h4 style={{ color: "#94a3b8", marginTop: 0, marginBottom: "16px", fontSize: "13px", textTransform: "uppercase", letterSpacing: "0.08em", fontWeight: "600" }}>
                            Orchestrator Feed
                        </h4>

                        {loading ? (
                            <div style={{ display: "flex", gap: "6px", alignItems: "center", height: "100px", justifyContent: "center" }}>
                                <div className="dot" style={{ width: "10px", height: "10px", backgroundColor: "#3b82f6", borderRadius: "50%", animation: "pulse 1s infinite" }}></div>
                                <div className="dot" style={{ width: "10px", height: "10px", backgroundColor: "#3b82f6", borderRadius: "50%", animation: "pulse 1s infinite 0.2s" }}></div>
                                <div className="dot" style={{ width: "10px", height: "10px", backgroundColor: "#3b82f6", borderRadius: "50%", animation: "pulse 1s infinite 0.4s" }}></div>
                            </div>
                        ) : (
                            <div style={{ 
                                whiteSpace: "pre-wrap", 
                                color: "#cbd5e1", 
                                lineHeight: "1.7",
                                fontSize: "15px"
                            }}>
                                {response || "Awaiting your command. Try typing a command to monitor your flight."}
                            </div>
                        )}
                    </div>
                </div>

                {/* Right Side: Live Monitoring Dashboard (conditional) */}
                {monitorSessionId && (
                    <div style={{ 
                        backgroundColor: "#111827", 
                        borderRadius: "20px", 
                        border: "1px solid #1f2937", 
                        padding: "28px",
                        display: "flex",
                        flexDirection: "column",
                        gap: "24px",
                        boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.3)"
                    }}>
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #1f2937", paddingBottom: "16px" }}>
                            <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
                                <div className="pulsing-green" style={{ width: "10px", height: "10px", borderRadius: "50%", backgroundColor: monitorState?.is_monitoring_active ? "#10b981" : "#ef4444" }} />
                                <h3 style={{ margin: 0, fontSize: "18px", fontWeight: "600", color: "white" }}>Ambient Flight Status</h3>
                            </div>
                            <span style={{ fontSize: "12px", padding: "4px 8px", backgroundColor: "#1f2937", borderRadius: "8px", color: "#94a3b8" }}>
                                {monitorState ? `Poll #${monitorState.delay_history?.length || 0}` : "Connecting..."}
                            </span>
                        </div>

                        {/* Flight & Meeting Overview */}
                        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "16px" }}>
                            <div style={{ backgroundColor: "#1e293b", padding: "16px", borderRadius: "12px", border: "1px solid #334155" }}>
                                <div style={{ fontSize: "12px", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>Flight Number</div>
                                <div style={{ fontSize: "20px", fontWeight: "700", color: "#f8fafc" }}>
                                    {flightDetails?.airlineCode} {flightDetails?.flightNumber}
                                </div>
                            </div>
                            <div style={{ backgroundColor: "#1e293b", padding: "16px", borderRadius: "12px", border: "1px solid #334155" }}>
                                <div style={{ fontSize: "12px", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "4px" }}>Live Status</div>
                                <div style={{ 
                                    fontSize: "18px", 
                                    fontWeight: "700", 
                                    color: (monitorState?.current_status || flightDetails?.initialStatus) === "on_time" ? "#10b981" : "#f43f5e" 
                                }}>
                                    {(monitorState?.current_status || flightDetails?.initialStatus || "on_time").toUpperCase().replace("_", " ")}
                                </div>
                            </div>
                        </div>

                        {/* Delay history timeline */}
                        <div>
                            <h4 style={{ margin: "0 0 12px 0", fontSize: "14px", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>Delay Log Progression</h4>
                            {monitorState?.delay_history && monitorState.delay_history.length > 0 ? (
                                <div style={{ display: "flex", gap: "8px", overflowX: "auto", paddingBottom: "8px" }}>
                                    {monitorState.delay_history.map((delay, idx) => (
                                        <div key={idx} style={{ 
                                            padding: "8px 12px", 
                                            backgroundColor: delay > 0 ? "rgba(244, 63, 94, 0.15)" : "rgba(16, 185, 129, 0.15)",
                                            border: delay > 0 ? "1px solid rgba(244, 63, 94, 0.3)" : "1px solid rgba(16, 185, 129, 0.3)",
                                            borderRadius: "10px",
                                            textAlign: "center",
                                            minWidth: "60px"
                                        }}>
                                            <div style={{ fontSize: "10px", color: "#94a3b8", marginBottom: "2px" }}>Poll {idx + 1}</div>
                                            <div style={{ fontSize: "14px", fontWeight: "700", color: delay > 0 ? "#f43f5e" : "#10b981" }}>
                                                {delay}m
                                            </div>
                                        </div>
                                    ))}
                                </div>
                            ) : (
                                <div style={{ color: "#64748b", fontSize: "14px", fontStyle: "italic" }}>
                                    Waiting for first polling update...
                                </div>
                            )}
                        </div>

                        {/* Decisions & Actions Log */}
                        <div style={{ backgroundColor: "#1e293b", borderRadius: "12px", padding: "20px", border: "1px solid #334155" }}>
                            <h4 style={{ margin: "0 0 14px 0", fontSize: "13px", color: "#94a3b8", textTransform: "uppercase", letterSpacing: "0.05em" }}>Negotiation Engine</h4>
                            <div style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "14px" }}>
                                    <span style={{ color: "#94a3b8" }}>Reschedule Required:</span>
                                    <span style={{ fontWeight: "600", color: monitorState?.email_sent ? "#ef4444" : "#10b981" }}>
                                        {monitorState?.email_sent ? "⚠️ Yes (Negotiating)" : "🟢 No"}
                                    </span>
                                </div>
                                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "14px" }}>
                                    <span style={{ color: "#94a3b8" }}>Email Dispatch Status:</span>
                                    <span style={{ fontWeight: "600", color: monitorState?.email_sent ? "#60a5fa" : "#64748b" }}>
                                        {monitorState?.email_sent ? "✉️ Sent Successfully" : "Idle"}
                                    </span>
                                </div>
                                {monitorState?.stop_reason && (
                                    <div style={{ 
                                        marginTop: "8px", 
                                        paddingTop: "12px", 
                                        borderTop: "1px solid #334155", 
                                        fontSize: "13px", 
                                        color: "#ef4444", 
                                        fontWeight: "600",
                                        textAlign: "center" 
                                    }}>
                                        🛑 Monitoring Finished: {monitorState.stop_reason}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>

            <style>{`
                @keyframes pulse {
                    0%, 100% { transform: scale(1); opacity: 1; }
                    50% { transform: scale(1.2); opacity: 0.5; }
                }
                .pulsing-green {
                    animation: pulse 1.5s infinite;
                }
            `}</style>
        </div>
    )
}