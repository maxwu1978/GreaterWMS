type ApiErrorLike = {
  response?: {
    data?: unknown;
    status?: number;
  };
  message?: string;
  errorCode?: string;
};

function fromResponseData(data: unknown): string | null {
  if (!data) return null;

  if (typeof data === "string") return data;

  if (Array.isArray(data)) {
    const nested = data.map(fromResponseData).filter(Boolean).join("; ");
    return nested || null;
  }

  if (typeof data === "object") {
    const record = data as Record<string, unknown>;

    if (typeof record.detail === "string") return record.detail;
    if (typeof record.error === "string") return record.error;
    if (typeof record.message === "string") return record.message;

    if (record.detail && typeof record.detail === "object" && !Array.isArray(record.detail)) {
      const detail = record.detail as Record<string, unknown>;
      if (typeof detail.message === "string") return detail.message;
      if (typeof detail.error === "string") return detail.error;
      if (typeof detail.msg === "string") return detail.msg;
    }

    if (Array.isArray(record.detail)) {
      const nested = record.detail
        .map((item) => {
          if (typeof item === "string") return item;
          if (item && typeof item === "object") {
            const obj = item as Record<string, unknown>;
            if (typeof obj.msg === "string") return obj.msg;
          }
          return null;
        })
        .filter(Boolean)
        .join("; ");
      if (nested) return nested;
    }
  }

  return null;
}

export function getApiErrorMessage(error: ApiErrorLike, fallback: string): string {
  const responseMessage = fromResponseData(error.response?.data);
  if (responseMessage) return responseMessage;

  if (!error.response && error.message) {
    return `Network error: ${error.message}`;
  }

  return fallback;
}

function codeFromResponseData(data: unknown): string | null {
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  const record = data as Record<string, unknown>;

  if (typeof record.error_code === "string") return record.error_code;
  if (typeof record.code === "string") return record.code;

  if (record.detail && typeof record.detail === "object" && !Array.isArray(record.detail)) {
    const detail = record.detail as Record<string, unknown>;
    if (typeof detail.error_code === "string") return detail.error_code;
    if (typeof detail.code === "string") return detail.code;
  }

  return null;
}

export function getApiErrorCode(error: ApiErrorLike | unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const record = error as ApiErrorLike;
  if (typeof record.errorCode === "string") return record.errorCode;
  return codeFromResponseData(record.response?.data);
}
