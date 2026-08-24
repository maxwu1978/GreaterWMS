import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowRight, KeyRound } from "lucide-react";
import { resetPassword, validatePasswordResetToken } from "../../shared/api/auth";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";
import PasswordInput from "../../shared/components/PasswordInput";

export default function ResetPasswordPage() {
  const { t } = useI18n();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = useMemo(() => searchParams.get("token") || "", [searchParams]);

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);
  const [validating, setValidating] = useState(true);
  const [tokenValid, setTokenValid] = useState(false);

  useEffect(() => {
    let active = true;

    async function validateToken() {
      if (!token) {
        setTokenValid(false);
        setError(t("auth.resetPasswordTokenMissing", "Reset link is missing or invalid."));
        setValidating(false);
        return;
      }

      try {
        const data = await validatePasswordResetToken(token);
        if (!active) return;
        setTokenValid(Boolean(data?.valid));
        if (!data?.valid) {
          setError(data?.message || t("auth.resetPasswordInvalid", "Reset link is invalid or expired."));
        }
      } catch (err: any) {
        if (!active) return;
        setTokenValid(false);
        setError(getApiErrorMessage(err, t("auth.resetPasswordInvalid", "Reset link is invalid or expired.")));
      } finally {
        if (active) setValidating(false);
      }
    }

    validateToken();
    return () => {
      active = false;
    };
  }, [token, t]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (password.length < 6) {
      setError(t("auth.passwordShort", "Password must be at least 6 characters"));
      return;
    }
    if (password !== confirmPassword) {
      setError(t("auth.passwordMismatch", "Passwords do not match"));
      return;
    }

    setLoading(true);
    try {
      await resetPassword(token, password);
      setSuccess(t("auth.resetPasswordSuccess", "Password updated. You can sign in now."));
      window.setTimeout(() => navigate("/login"), 1200);
    } catch (err: any) {
      setError(getApiErrorMessage(err, t("auth.resetPasswordError", "Could not reset password.")));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#f2efe8] px-5 py-10 text-[#13212c] md:px-8">
      <div className="mx-auto max-w-xl">
        <div className="rounded-[2rem] border border-[#13212c]/10 bg-white/80 p-8 shadow-[0_28px_60px_rgba(19,33,44,0.08)] backdrop-blur">
          <div className="flex items-center justify-between gap-3">
            <Link to="/login" className="text-xs uppercase tracking-[0.28em] text-[#7a8894]">
              {t("auth.backToSignIn", "Back to sign in")}
            </Link>
          </div>

          <div className="mt-8 flex items-center gap-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-3xl border border-[#13212c]/10 bg-[#f7f4ee] text-[#13212c]">
              <KeyRound size={24} />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[#7a8894]">
                {t("auth.resetPasswordEyebrow", "Reset password")}
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-[#13212c]">
                {t("auth.resetPasswordTitle", "Choose a new password")}
              </h1>
            </div>
          </div>

          <p className="mt-5 text-sm leading-7 text-[#5b6a77]">
            {t(
              "auth.resetPasswordBody",
              "Set a new password for your workspace account. Once saved, the old password will stop working."
            )}
          </p>

          {validating ? (
            <p className="mt-6 rounded-2xl border border-[#13212c]/10 bg-[#f7f4ee] px-4 py-3 text-sm text-[#5b6a77]">
              {t("common.loading", "Loading...")}
            </p>
          ) : null}

          {!validating && tokenValid ? (
            <form onSubmit={handleSubmit} className="mt-8 space-y-4">
              <div>
                <label htmlFor="reset-password" className="mb-1.5 block text-sm font-medium text-[#334351]">
                  {t("auth.newPassword", "New password")}
                </label>
                <PasswordInput
                  id="reset-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                />
              </div>

              <div>
                <label htmlFor="reset-confirm-password" className="mb-1.5 block text-sm font-medium text-[#334351]">
                  {t("auth.confirmNewPassword", "Confirm new password")}
                </label>
                <PasswordInput
                  id="reset-confirm-password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  required
                  className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                />
              </div>

              {error ? (
                <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">{error}</p>
              ) : null}

              {success ? (
                <p className="rounded-2xl border border-[#b8d8c3] bg-[#edf8f1] px-4 py-3 text-sm text-[#1b5f38]">
                  {success}
                </p>
              ) : null}

              <button
                type="submit"
                disabled={loading}
                className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-[#13212c] px-5 py-3.5 text-sm font-semibold uppercase tracking-[0.14em] text-[#f6f2ea] transition hover:bg-[#1c2f3d] disabled:opacity-50"
              >
                {loading
                  ? t("auth.resettingPassword", "Saving new password...")
                  : t("auth.resetPasswordAction", "Save new password")}
                <ArrowRight size={16} />
              </button>
            </form>
          ) : null}

          {!validating && !tokenValid ? (
            <div className="mt-8 space-y-4">
              <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                {error || t("auth.resetPasswordInvalid", "Reset link is invalid or expired.")}
              </p>
              <Link
                to="/forgot-password"
                className="inline-flex items-center gap-2 text-sm font-semibold text-[#13212c]"
              >
                {t("auth.sendResetLink", "Send reset link")}
                <ArrowRight size={15} />
              </Link>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
