import { Component } from "react";

/**
 * Catches render errors so one broken page cannot blank the whole application.
 *
 * Without this, a single unexpected API shape throws during render, React
 * unmounts the entire tree, and the user gets a white screen with no
 * explanation — the navigation disappears too, so there is no way back.
 * With it, the failure is contained: the rail still works and the error names
 * what actually went wrong.
 */
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep the stack in the console for debugging; the UI stays readable.
    console.error("Render error:", error, info?.componentStack);
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;

    const message = error?.message || String(error);
    // The commonest cause is the API returning a shape the page did not expect,
    // which in practice means a different backend is answering on the port.
    const looksLikeShapeMismatch =
      /is not a function|undefined|Cannot read|not iterable/i.test(message);

    return (
      <div className="page">
        <div className="state state--error" role="alert">
          <div className="state__title">This page could not render</div>
          <div className="state__body">{message}</div>

          {looksLikeShapeMismatch && (
            <div className="state__body tiny muted" style={{ marginTop: 8 }}>
              This usually means the API returned data in an unexpected shape.
              Check that the ReviveAI backend is the one answering on port 8000 —
              open <code>/api/health</code> and confirm it lists{" "}
              <code>models_trained</code>. Another project running on the same
              port will return a different shape.
            </div>
          )}

          <div className="row" style={{ marginTop: 12 }}>
            <button type="button" className="btn" onClick={this.reset}>
              Try again
            </button>
            <button
              type="button"
              className="btn"
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
          </div>
        </div>
      </div>
    );
  }
}
