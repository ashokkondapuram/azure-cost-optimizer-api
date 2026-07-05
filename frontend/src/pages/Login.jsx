import React, { useState, useContext, useMemo } from 'react';
import { Navigate, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { LogIn, LineChart, Server, Zap } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { AppCtx } from '../App';
import { getErrorMessage } from '../api/errors';
import InfinityOpsLogo, { InfinityOpsWordmark } from '../components/brand/InfinityOpsLogo';
import ThemeToggle from '../components/ThemeToggle';
import {
  APP_TAGLINE,
  LOGIN_CARD_SUBTITLE,
  LOGIN_FEATURES,
  LOGIN_HERO_DESC,
  LOGIN_HERO_TITLE,
} from '../config/appRegistry';

import { postLoginPath } from '../utils/authRedirect';

const FEATURE_ICONS = {
  cost: { icon: LineChart, color: '#0ea5e9' },
  inventory: { icon: Server, color: '#6366f1' },
  optimize: { icon: Zap, color: '#38bdf8' },
};

export default function Login() {
  const { login, isAuthenticated, loading } = useAuth();
  const { reloadSubscriptions } = useContext(AppCtx);
  const location = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const from = useMemo(
    () => postLoginPath(searchParams, location.state),
    [searchParams, location.state],
  );

  if (!loading && isAuthenticated && !submitting) {
    return <Navigate to={from} replace />;
  }

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
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="login-page login-page--animated">
      <div className="login-page__theme login-page__theme--enter">
        <ThemeToggle compact />
      </div>
      <div className="login-page__bg" aria-hidden="true">
        <div className="login-page__orb login-page__orb--1" />
        <div className="login-page__orb login-page__orb--2" />
        <div className="login-page__orb login-page__orb--3" />
        <div className="login-page__grid" />
      </div>

      <div className="login-layout login-layout--enter">
        <section className="login-hero login-hero--enter">
          <div className="login-hero__badge login-hero__item login-hero__item--1">{APP_TAGLINE}</div>
          <h2 className="login-hero__title login-hero__item login-hero__item--2">{LOGIN_HERO_TITLE}</h2>
          <p className="login-hero__desc login-hero__item login-hero__item--3">{LOGIN_HERO_DESC}</p>
          <ul className="login-hero__features">
            {LOGIN_FEATURES.map(({ id, label, desc }, index) => {
              const { icon: Icon, color } = FEATURE_ICONS[id] || FEATURE_ICONS.cost;
              return (
                <li
                  key={id}
                  className={`login-hero__item login-hero__item--feature login-hero__item--${index + 4}`}
                  style={{ '--feature-color': color }}
                >
                  <span className="login-hero__feature-icon">
                    <Icon size={16} />
                  </span>
                  <span className="login-hero__feature-copy">
                    <strong>{label}</strong>
                    <span>{desc}</span>
                  </span>
                </li>
              );
            })}
          </ul>
        </section>

        <div className="login-card login-card--enter">
          <div className="login-card__brand">
            <div className="sidebar-logo__icon sidebar-logo__icon--brand login-card__logo login-card__logo--pulse">
              <InfinityOpsLogo size={40} />
            </div>
            <InfinityOpsWordmark className="login-card__wordmark" />
            <p>{LOGIN_CARD_SUBTITLE}</p>
          </div>

          <form className="login-form" onSubmit={handleSubmit}>
            {error && (
              <div className="alert alert--danger" role="alert">
                {error}
              </div>
            )}

            <label className="login-form__field login-form__field--enter login-form__field--1">
              <span>Username</span>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter username"
                required
                disabled={submitting}
              />
            </label>

            <label className="login-form__field login-form__field--enter login-form__field--2">
              <span>Password</span>
              <input
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter password"
                required
                disabled={submitting}
              />
            </label>

            <button
              type="submit"
              className="btn btn-primary login-form__submit login-form__field--enter login-form__field--3"
              disabled={submitting}
            >
              <LogIn size={16} />
              {submitting ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
