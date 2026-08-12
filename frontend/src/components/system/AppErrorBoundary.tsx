import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  failed: boolean;
}

export class AppErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Nova application boundary', error, info.componentStack);
  }

  private recover = (): void => {
    window.location.reload();
  };

  render(): ReactNode {
    if (!this.state.failed) return this.props.children;
    return (
      <main className="nova-shell flex min-h-dvh items-center justify-center p-6">
        <section className="nova-panel w-full max-w-md rounded-3xl p-8 text-center" role="alert">
          <AlertTriangle className="mx-auto mb-5 h-10 w-10 text-amber-400" aria-hidden="true" />
          <h1 className="text-xl font-semibold text-foreground">Nova needs a clean restart</h1>
          <p className="mt-3 text-sm leading-6 text-muted-foreground">
            Your secure session can be restored from the HttpOnly cookie. Reload the workspace to reconnect.
          </p>
          <button
            type="button"
            onClick={this.recover}
            className="mt-6 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 text-sm font-semibold text-primary-foreground"
          >
            <RefreshCw className="h-4 w-4" aria-hidden="true" />
            Restore session
          </button>
        </section>
      </main>
    );
  }
}
