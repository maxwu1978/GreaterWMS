import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Mail } from "lucide-react";
import { requestPasswordReset } from "../../shared/api/auth";
import { getApiErrorMessage } from "../../shared/api/error-message";
import { useI18n } from "../../shared/i18n";

export default function ForgotPasswordPage() {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError("");
    setSuccess("");
    setLoading(true);

    try {
      const data = await requestPasswordReset(email);
      setSuccess(
        data?.message ||
          t(
            "auth.forgotPasswordSuccess",
            "If that email exists, a password reset link has been sent."
          )
      );
    } catch (err: any) {
      setError(getApiErrorMessage(err, t("auth.forgotPasswordError", "Could not send reset email.")));
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
              <Mail size={24} />
            </div>
            <div>
              <p className="text-xs uppercase tracking-[0.24em] text-[#7a8894]">
                {t("auth.forgotPasswordEyebrow", "Password recovery")}
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-[-0.03em] text-[#13212c]">
                {t("auth.forgotPasswordTitle", "Reset your password")}
              </h1>
            </div>
          </div>

          <p className="mt-5 text-sm leading-7 text-[#5b6a77]">
            {t(
              "auth.forgotPasswordBody",
              "Enter the email linked to your workspace. If the account exists, we will send a secure reset link."
            )}
          </p>

          <form onSubmit={handleSubmit} className="mt-8 space-y-4">
            <div>
              <label htmlFor="forgot-email" className="mb-1.5 block text-sm font-medium text-[#334351]">
                {t("auth.email", "Email")}
              </label>
              <input
                id="forgot-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                className="w-full rounded-2xl border border-[#13212c]/12 bg-white px-4 py-3 text-[#13212c] outline-none transition focus:border-[#13212c]/30 focus:ring-4 focus:ring-[#13212c]/5"
                placeholder="operator@warehouse.com"
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
                ? t("auth.sendingResetLink", "Sending reset link...")
                : t("auth.sendResetLink", "Send reset link")}
              <ArrowRight size={16} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
