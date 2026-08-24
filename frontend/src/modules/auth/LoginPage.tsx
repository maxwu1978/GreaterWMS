import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Boxes } from "lucide-react";
import { defaultRouteForRole, useAuthStore } from "../../shared/hooks/useAuth";
import { login } from "../../shared/api/auth";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";
import PasswordInput from "../../shared/components/PasswordInput";

export default function LoginPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [acceptNotice, setAcceptNotice] = useState(false);
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const data = await login(email, password);
      setAuth(data.access_token, data.role, data.tenant_id, data.job_title, data.permissions || []);
      navigate(defaultRouteForRole(data.role));
    } catch (err: any) {
      setError(getApiErrorMessage(err, t("common.signIn", "Sign in") + " failed"));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-[100dvh] items-center justify-center bg-[#f2efe8] px-5 pb-[env(safe-area-inset-bottom)] pt-[env(safe-area-inset-top)] text-[#13212c]">
      <div className="w-full max-w-sm">
        <div className="rounded-[2rem] border border-[#13212c]/10 bg-white/82 p-8 shadow-[0_18px_42px_rgba(19,33,44,0.08)] backdrop-blur">
          <Link to="/" className="flex items-center gap-3">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-full bg-[#13212c] text-[#f6f2ea]">
              <Boxes size={16} />
            </span>
            <span className="text-sm font-semibold">WMS QuickStart</span>
          </Link>

          <h1 className="mt-6 text-2xl font-semibold leading-tight">
            {t("common.signIn", "Sign in")}
          </h1>

          <form onSubmit={handleSubmit} className="mt-5 space-y-3">
            <input
              id="login-email"
              type="email"
              aria-label={t("auth.email", "Email")}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
              placeholder={t("auth.email", "Email")}
            />

            <PasswordInput
              id="login-password"
              aria-label={t("auth.password", "Password")}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              placeholder={t("auth.password", "Password")}
              className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-sm text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
            />

            {error && (
              <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
            )}

            <label className="flex items-start gap-2.5 px-1 pt-1 text-sm leading-6 text-[#586773]">
              <input
                type="checkbox"
                checked={acceptNotice}
                onChange={(e) => setAcceptNotice(e.target.checked)}
                className="mt-1 h-4 w-4 shrink-0 accent-[#13212c]"
              />
              <span>
                {t("auth.loginNoticeShort", "I accept the live data access responsibility notice.")}{" "}
                <details className="inline-block align-baseline">
                  <summary className="inline cursor-pointer list-none text-xs text-[#7a8894] underline underline-offset-2">
                    {t("legal.viewSignInNotice", "View notice")}
                  </summary>
                  <span className="mt-1 block text-xs leading-5 text-[#7a8894]">
                    {t(
                      "legal.liveDataAccessBody",
                      "Signing in may expose live customer, inventory, shipment, billing, and warehouse planning data. Access is limited to authorized users; each user remains responsible for lawful use, careful data handling, and client confidentiality."
                    )}
                  </span>
                </details>
              </span>
            </label>

            <button
              type="submit"
              disabled={loading || !acceptNotice}
              className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3 text-sm font-semibold uppercase tracking-[0.08em] text-[#f6f2ea] transition hover:bg-[#1c2f3d] disabled:opacity-50"
            >
              {loading ? t("auth.signingIn", "Signing in...") : t("common.signIn", "Sign in")}
              <ArrowRight size={16} />
            </button>

            <div className="flex items-center justify-between pt-1 text-sm">
              <Link to="/forgot-password" className="font-medium text-[#13212c] underline-offset-4 hover:underline">
                {t("auth.forgotPassword", "Forgot password?")}
              </Link>
              <Link to="/register" className="font-medium text-[#13212c] underline-offset-4 hover:underline">
                {t("common.startTrial", "Start trial")}
              </Link>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
