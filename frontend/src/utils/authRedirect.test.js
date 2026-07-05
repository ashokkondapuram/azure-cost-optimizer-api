import { loginPathWithNext, postLoginPath } from './authRedirect';

describe('authRedirect', () => {
  it('reads next query param', () => {
    const params = new URLSearchParams('next=%2Fk8s');
    expect(postLoginPath(params, null)).toBe('/k8s');
  });

  it('falls back to router state location', () => {
    expect(postLoginPath(new URLSearchParams(), {
      from: { pathname: '/k8s', search: '', hash: '' },
    })).toBe('/k8s');
  });

  it('defaults to dashboard', () => {
    expect(postLoginPath(new URLSearchParams(), null)).toBe('/');
  });

  it('builds login path with next', () => {
    expect(loginPathWithNext('/k8s')).toBe('/login?next=%2Fk8s');
  });

  it('rejects open redirects and API paths', () => {
    expect(postLoginPath(new URLSearchParams('next=%2F%2Fevil.com'), null)).toBe('/');
    expect(postLoginPath(new URLSearchParams('next=%2Fresources%2Fvms'), null)).toBe('/');
    expect(postLoginPath(new URLSearchParams('next=%2Flogin'), null)).toBe('/');
    expect(postLoginPath(new URLSearchParams('next=%2Floginfoo'), null)).toBe('/loginfoo');
  });
});
