import { Component, type ErrorInfo, type ReactNode } from 'react'
import { RotateCcw } from 'lucide-react'

interface Props {
  children: ReactNode
}

interface State {
  hasError: boolean
  message: string
}

/**
 * FE-002：顶层错误边界。
 * 捕获渲染期异常，避免整页白屏，提供重试（重置边界）与刷新入口。
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: '' }

  static getDerivedStateFromError(error: unknown): State {
    return { hasError: true, message: error instanceof Error ? error.message : '页面渲染出现问题' }
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    // 保留控制台记录，便于本地调试；生产可接入上报。
    console.error('渲染错误被 ErrorBoundary 捕获：', error, info.componentStack)
  }

  private handleReset = () => {
    this.setState({ hasError: false, message: '' })
  }

  render() {
    if (!this.state.hasError) return this.props.children
    return (
      <div className="app-error" role="alert">
        <div className="app-error-card">
          <h1>页面出了点问题</h1>
          <p>这一部分暂时无法显示，你可以重试，或刷新整个页面。</p>
          {this.state.message ? <small className="app-error-detail">{this.state.message}</small> : null}
          <div className="app-error-actions">
            <button className="primary-button" type="button" onClick={this.handleReset}><RotateCcw size={17} /> 重试</button>
            <button className="secondary-button" type="button" onClick={() => window.location.assign('/')}>返回首页</button>
          </div>
        </div>
      </div>
    )
  }
}
