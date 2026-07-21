import React, {
  useCallback,
  useContext,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import {
  Eye,
  EyeOff,
  Loader2,
  Lock,
  LogIn,
  ShieldCheck,
  User,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { AppCtx } from '../App';
import { getErrorMessage } from '../api/errors';
import InfinityOpsLogo, { InfinityOpsWordmark } from '../components/brand/InfinityOpsLogo';
import LoginFeatureShowcase from '../components/login/LoginFeatureShowcase';
import { LoginHeroTitleBlock } from '../components/login/OptimizationTitleAccent';
import {
  APP_NAME,
  LOGIN_CARD_SUBTITLE,
  LOGIN_HERO_DESC,
  LOGIN_HERO_TITLE,
  LOGIN_OPTIMIZATION_REVEALS,
} from '../config/appRegistry';

import { postLoginPath } from '../utils/authRedirect';

export default function Login() {
  const { login, isAuthenticated, loading } = useAuth();
  const { reloadSubscriptions } = useContext(AppCtx);
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const pageRef = useRef(null);
  const usernameRef = useRef(null);

  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [shake, setShake] = useState(false);

  const from = useMemo(
    () => postLoginPath(searchParams, location.state),
    [searchParams, location.state],
  );

  const handleParallax = useCallback((event) => {
    const node = pageRef.current;
    if (!node) return;
    const rect = node.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) - 0.5;
    const y = ((event.clientY - rect.top) / rect.height) - 0.5;
    node.style.setProperty('--parallax-x', `${x * 28}px`);
    node.style.setProperty('--parallax-y', `${y * 18}px`);
  }, []);

  const resetParallax = useCallback(() => {
    const node = pageRef.current;
    if (!node) return;
    node.style.setProperty('--parallax-x', '0px');
    node.style.setProperty('--parallax-y', '0px');
  }, []);

  if (!loading && isAuthenticated && !submitting) {
    return <Navigate to={from} replace />;
  }

  const triggerShake = () => {
    setShake(true);
    window.setTimeout(() => setShake(false), 520);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    const target = postLoginPath(searchParams, location.state);
    try {
      await login(username.trim(), password);
      navigate(target, { replace: true });
      reloadSubscriptions?.();
    } catch (err) {
      setError(getErrorMessage(err, 'Sign in failed. Check your username and password.'));
      triggerShake();
      usernameRef.current?.focus();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      ref={pageRef}
      className="login-page login-page--animated"
      onMouseMove={handleParallax}
      onMouseLeave={resetParallax}
    >
      <div className="login-page__bg" aria-hidden="true">
        <div className="login-page__aurora" />
        <div className="login-page__noise" />
        <div className="login-page__orb login-page__orb--1" />
        <div className="login-page__orb login-page__orb--2" />
        <div className="login-page__orb login-page__orb--3" />
        <div className="login-page__grid" />
        <div className="login-page__glow" />
      </div>

      <div className="login-layout login-layout--enter">
        <section className="login-hero login-hero--enter" aria-labelledby="login-hero-title">
          <p className="login-hero__eyebrow login-hero__item login-hero__item--1">{APP_NAME}</p>
          <LoginHeroTitleBlock
            id="login-hero-title"
            title={LOGIN_HERO_TITLE}
            reveals={LOGIN_OPTIMIZATION_REVEALS}
            blockClassName="login-hero__item login-hero__item--2"
            className="login-hero__title"
          />
          <p className="login-hero__desc login-hero__item login-hero__item--3">{LOGIN_HERO_DESC}</p>
          <LoginFeatureShowcase className="login-hero__item login-hero__item--4" />
        </section>

        <div className={`login-card-wrap login-card--enter${shake ? ' login-card--shake' : ''}`}>
        <div className="login-card">
          <div className="login-card__brand">
            <div className="sidebar-logo__icon sidebar-logo__icon--brand login-card__logo login-card__logo--pulse">
              <InfinityOpsLogo size={44} />
            </div>
            <InfinityOpsWordmark className="login-card__wordmark" />
            <p>{LOGIN_CARD_SUBTITLE}</p>
          </div>

          <div className="login-card__divider" aria-hidden="true" />

          <form className="login-form" onSubmit={handleSubmit} noValidate>
            {error && (
              <div className="login-form__alert alert alert--danger" role="alert">
                {error}
              </div>
            )}

            <label className="login-form__field login-form__field--enter login-form__field--1">
              <span>Username</span>
              <span className="login-form__input-wrap">
                <User size={16} className="login-form__input-icon" aria-hidden />
                <input
                  ref={usernameRef}
                  type="text"
                  autoComplete="username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Enter username"
                  required
                  disabled={submitting}
                  aria-invalid={Boolean(error)}
                />
              </span>
            </label>

            <label className="login-form__field login-form__field--enter login-form__field--2">
              <span>Password</span>
              <span className="login-form__input-wrap">
                <Lock size={16} className="login-form__input-icon" aria-hidden />
                <input
                  type={showPassword ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Enter password"
                  required
                  disabled={submitting}
                  aria-invalid={Boolean(error)}
                />
                <button
                  type="button"
                  className="login-form__toggle-password"
                  onClick={() => setShowPassword((v) => !v)}
                  disabled={submitting}
                  aria-label={showPassword ? 'Hide password' : 'Show password'}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </span>
            </label>

            <button
              type="submit"
              className="btn btn-primary login-form__submit login-form__field--enter login-form__field--3"
              disabled={submitting || !username.trim() || !password}
            >
              {submitting ? <Loader2 size={16} className="login-form__spinner" aria-hidden /> : <LogIn size={16} />}
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          <p className="login-card__secure">
            <ShieldCheck size={14} aria-hidden />
            Operations team access only
          </p>
        </div>
        </div>
      </div>
    </div>
  );
}
