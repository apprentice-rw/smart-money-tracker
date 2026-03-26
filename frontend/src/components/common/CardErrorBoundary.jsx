import React from 'react';

class CardErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('InstitutionCard render error:', error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-white border border-red-100 rounded-3xl shadow-lg p-5">
          <p className="text-sm font-semibold text-red-400 mb-1">Failed to render card</p>
          <p className="text-xs text-gray-400">{this.state.error?.message}</p>
        </div>
      );
    }
    return this.props.children;
  }
}

export default CardErrorBoundary;
