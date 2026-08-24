import { useState, type InputHTMLAttributes } from "react";
import { Eye, EyeOff } from "lucide-react";
import clsx from "clsx";
import { useI18n } from "../i18n";

type PasswordInputProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type"> & {
  wrapperClassName?: string;
};

export default function PasswordInput({ className, wrapperClassName, style, ...props }: PasswordInputProps) {
  const { t } = useI18n();
  const [visible, setVisible] = useState(false);
  const label = visible ? t("common.hidePassword", "Hide password") : t("common.showPassword", "Show password");

  return (
    <div className={clsx("relative", wrapperClassName)}>
      <input
        {...props}
        type={visible ? "text" : "password"}
        style={{ ...style, paddingRight: "3rem" }}
        className={className}
      />
      <button
        type="button"
        aria-label={label}
        title={label}
        onClick={() => setVisible((current) => !current)}
        className="absolute right-3 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full text-[#61717d] transition hover:bg-[#13212c]/6 hover:text-[#13212c] focus:outline-none focus:ring-4 focus:ring-[#13212c]/10"
      >
        {visible ? <EyeOff size={17} /> : <Eye size={17} />}
      </button>
    </div>
  );
}
