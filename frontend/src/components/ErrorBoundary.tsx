import React from 'react';

type Props = { children: React.ReactNode };
type State = { error: Error | null; info: React.ErrorInfo | null };

class ErrorBoundary extends React.Component<Props, State> {
  state: State = { error: null, info: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    this.setState({ info });
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] caught:', error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div
          style={{
            minHeight: '100vh',
            padding: 32,
            background: '#1e2229',
            color: '#fca5a5',
            fontFamily:
              'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            fontSize: 13,
            lineHeight: 1.55,
            overflowX: 'auto',
          }}
        >
          <h2 style={{ color: '#ef4444', marginTop: 0 }}>UI crashed</h2>
          <div style={{ color: '#fef3c7', marginBottom: 16 }}>
            {this.state.error.name}: {this.state.error.message}
          </div>
          <details open style={{ marginBottom: 16 }}>
            <summary style={{ cursor: 'pointer', color: '#9fb0c6' }}>
              stack trace
            </summary>
            <pre style={{ whiteSpace: 'pre-wrap', color: '#fca5a5' }}>
              {this.state.error.stack}
            </pre>
          </details>
          {this.state.info?.componentStack && (
            <details>
              <summary style={{ cursor: 'pointer', color: '#9fb0c6' }}>
                react component stack
              </summary>
              <pre style={{ whiteSpace: 'pre-wrap', color: '#94a3b8' }}>
                {this.state.info.componentStack}
              </pre>
            </details>
          )}
          <button
            onClick={() => this.setState({ error: null, info: null })}
            style={{
              marginTop: 16,
              padding: '8px 16px',
              background: '#10b981',
              color: '#1e2229',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              fontWeight: 'bold',
            }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
