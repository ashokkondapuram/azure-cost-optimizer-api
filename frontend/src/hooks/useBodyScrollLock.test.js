import { lockBodyScroll } from './useBodyScrollLock';

describe('lockBodyScroll', () => {
  beforeEach(() => {
    document.body.removeAttribute('style');
    window.scrollTo(0, 0);
  });

  afterEach(() => {
    document.body.removeAttribute('style');
    window.scrollTo(0, 0);
    jest.restoreAllMocks();
  });

  it('preserves scroll position while locked and restores it on unlock', () => {
    const scrollToSpy = jest.spyOn(window, 'scrollTo').mockImplementation(() => {});

    const unlock = lockBodyScroll(480);

    expect(document.body.style.position).toBe('fixed');
    expect(document.body.style.top).toBe('-480px');
    expect(document.body.style.overflow).toBe('hidden');

    unlock();

    expect(document.body.style.position).toBe('');
    expect(scrollToSpy).toHaveBeenCalledWith(0, 480);
  });

  it('uses ref counting so nested locks restore only after the last unlock', () => {
    const scrollToSpy = jest.spyOn(window, 'scrollTo').mockImplementation(() => {});

    const unlockA = lockBodyScroll(120);
    const unlockB = lockBodyScroll(120);

    expect(document.body.style.position).toBe('fixed');

    unlockA();
    expect(document.body.style.position).toBe('fixed');
    expect(scrollToSpy).not.toHaveBeenCalled();

    unlockB();
    expect(document.body.style.position).toBe('');
    expect(scrollToSpy).toHaveBeenCalledWith(0, 120);
  });
});
