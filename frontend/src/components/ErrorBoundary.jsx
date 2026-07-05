import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // eslint-disable-next-line no-console
    console.error('UI error boundary caught:', error, info);
  }

  render() {
    const { error } = this.state;
    if (error) {
      return (
        <div className="card empty-state" role="alert" style={{ margin: '2rem' }}>
          <p style={{ color: 'var(--danger)', fontWeight: 600 }}>Something went wrong</p>
          <p style={{ color: 'var(--text2)', fontSize: '0.86rem' }}>
            {error?.message || String(error) || 'An unexpected error occurred in this view.'}
          </p>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ marginTop: '1rem' }}
            onClick={() => this.setState({ error: null })}
          >
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
