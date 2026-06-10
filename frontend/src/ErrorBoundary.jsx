import { Component } from "react";
import PropTypes from "prop-types";
import { S } from "./tokens";

/** Catches render errors so one broken page/feature can't blank the app.
 *  Mounted at the app root (main.jsx) and around each page (App.jsx, keyed
 *  by page id so navigating away resets it). */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("ErrorBoundary caught:", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div role="alert" style={{ margin: 24, padding: 24, borderRadius: 14, background: "var(--errL)", border: "1px solid rgba(220,38,38,.25)", color: S.err, fontFamily: "'DM Sans Variable','Segoe UI',sans-serif" }}>
        <b style={{ display: "block", fontSize: 15, marginBottom: 6 }}>{this.props.title || "Something went wrong"}</b>
        <p style={{ margin: "0 0 14px", fontSize: 13, color: S.g600 }}>
          {this.props.message || "The error has been logged. Try reloading the page."}
        </p>
        <button
          onClick={() => { this.setState({ error: null }); this.props.onReset?.(); }}
          style={{ padding: "8px 16px", borderRadius: 10, border: "none", background: S.err, color: "#fff", fontSize: 13, fontWeight: 600, cursor: "pointer", fontFamily: "inherit" }}
        >
          {this.props.retryLabel || "Try again"}
        </button>
      </div>
    );
  }
}

ErrorBoundary.propTypes = {
  children: PropTypes.node,
  title: PropTypes.string,
  message: PropTypes.string,
  retryLabel: PropTypes.string,
  onReset: PropTypes.func,
};
