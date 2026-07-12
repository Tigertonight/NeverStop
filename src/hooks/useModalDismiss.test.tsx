import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useModalDismiss } from './useModalDismiss'

function Dialog({ onClose }: { onClose: () => void }) {
  const ref = useModalDismiss<HTMLDivElement>(onClose)
  return (
    <div ref={ref} role="dialog" aria-modal="true" tabIndex={-1}>
      <button>first</button>
      <button>second</button>
      <button>third</button>
    </div>
  )
}

describe('useModalDismiss', () => {
  it('moves focus to the first focusable element on open', () => {
    render(<Dialog onClose={() => {}} />)
    expect(screen.getByText('first')).toHaveFocus()
  })

  it('closes on Escape', async () => {
    const onClose = vi.fn()
    const user = userEvent.setup()
    render(<Dialog onClose={onClose} />)
    await user.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('traps Tab focus within the dialog (wraps last -> first)', async () => {
    const user = userEvent.setup()
    render(<Dialog onClose={() => {}} />)
    const [first, , third] = screen.getAllByRole('button')
    third.focus()
    await user.tab()
    expect(first).toHaveFocus()
  })

  it('wraps Shift+Tab from first -> last', async () => {
    const user = userEvent.setup()
    render(<Dialog onClose={() => {}} />)
    const buttons = screen.getAllByRole('button')
    buttons[0].focus()
    await user.tab({ shift: true })
    expect(buttons[buttons.length - 1]).toHaveFocus()
  })

  it('restores focus to the previously focused element on unmount', () => {
    const trigger = document.createElement('button')
    trigger.textContent = 'trigger'
    document.body.appendChild(trigger)
    trigger.focus()
    expect(trigger).toHaveFocus()

    const { unmount } = render(<Dialog onClose={() => {}} />)
    expect(screen.getByText('first')).toHaveFocus()
    unmount()
    expect(trigger).toHaveFocus()
    trigger.remove()
  })
})
