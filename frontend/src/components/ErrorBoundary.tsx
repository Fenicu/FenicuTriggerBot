import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    this.setState({ errorInfo });

    // Log error to console in development
    if (import.meta.env.DEV) {
      console.error('ErrorBoundary caught an error:', error, errorInfo);
    }
  }

  handleReload = (): void => {
    window.location.reload();
  };

  handleReset = (): void => {
    this.setState({ hasError: false, error: null, errorInfo: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-bg text-text p-4">
          <div className="bg-surface p-8 rounded-2xl shadow-lg max-w-md w-full text-center">
            <div className="w-16 h-16 bg-danger-soft rounded-full flex items-center justify-center mx-auto mb-6">
              <AlertTriangle className="text-danger" size={32} />
            </div>

            <h1 className="text-xl font-bold mb-2">Что-то пошло не так</h1>
            <p className="text-hint mb-6">
              Произошла непредвиденная ошибка. Попробуйте обновить страницу.
            </p>

            {import.meta.env.DEV && this.state.error && (
              <div className="bg-danger-soft border border-danger/20 rounded-lg p-4 mb-6 text-left">
                <p className="text-danger text-sm font-mono break-all">
                  {this.state.error.message}
                </p>
                {this.state.errorInfo && (
                  <details className="mt-2">
                    <summary className="text-hint text-xs cursor-pointer">
                      Трассировка стека
                    </summary>
                    <pre className="text-xs text-hint mt-2 overflow-auto max-h-40">
                      {this.state.errorInfo.componentStack}
                    </pre>
                  </details>
                )}
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={this.handleReset}
                className="flex-1 py-3 px-4 rounded-xl font-medium bg-elevated hover:bg-elevated transition-colors"
              >
                Повторить
              </button>
              <button
                onClick={this.handleReload}
                className="flex-1 py-3 px-4 rounded-xl font-medium bg-button text-button-text hover:opacity-90 transition-colors flex items-center justify-center gap-2"
              >
                <RefreshCw size={18} />
                Обновить
              </button>
            </div>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
