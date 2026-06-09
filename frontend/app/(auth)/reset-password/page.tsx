"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button, Card, Input } from "@/src/components/ui";
import { Logo } from "@/src/components/Logo";

type ApiErrorResponse = {
  detail?: string | string[];
  [key: string]: unknown;
};

export default function ResetPasswordPage() {
  const searchParams = useSearchParams();
  const uid = searchParams.get("uid");
  const token = searchParams.get("token");

  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [message, setMessage] = useState(
    !uid || !token ? "Invalid password reset link." : ""
  );
  const [messageType, setMessageType] = useState<"success" | "error" | "">(
    !uid || !token ? "error" : ""
  );
  const [isLoading, setIsLoading] = useState(false);

  function formatErrorMessage(data: ApiErrorResponse) {
    if (data.detail) {
      return Array.isArray(data.detail) ? data.detail.join(" ") : data.detail;
    }

    return Object.entries(data)
      .map(([field, messages]) => {
        if (Array.isArray(messages)) {
          return `${field}: ${messages.join(" ")}`;
        }

        return `${field}: ${String(messages)}`;
      })
      .join("\n");
  }

  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault();

    setMessage("");
    setMessageType("");

    if (!uid || !token) {
      setMessageType("error");
      setMessage("Invalid password reset link.");
      return;
    }

    const passwordRegex =
      /^(?=.*[A-Za-z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>_\-+=/\\[\]~`]).{8,}$/;

    if (!passwordRegex.test(password)) {
      setMessageType("error");
      setMessage(
        "Password must be at least 8 characters and include at least one letter, one digit, and one special character."
      );
      return;
    }

    if (password !== confirmPassword) {
      setMessageType("error");
      setMessage("Passwords do not match.");
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/auth/password-reset/confirm/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            uid,
            token,
            password,
            confirm_password: confirmPassword,
          }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        setMessageType("error");
        setMessage(formatErrorMessage(data));
        return;
      }

      setMessageType("success");
      setMessage(data.detail || "Password reset successfully.");
      setPassword("");
      setConfirmPassword("");
    } catch (error) {
      console.error("Reset password error:", error);
      setMessageType("error");
      setMessage("Something went wrong. Please make sure Django backend is running.");
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-600 to-sky-500 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo size="lg" theme="dark" layout="vertical" />

          <p className="mt-4 text-base font-semibold text-white/85">
            Set a new MomentumQuest password
          </p>
        </div>

        <Card className="p-8">
          <h1 className="mb-2 text-3xl font-bold text-gray-950">
            Reset password
          </h1>

          <p className="mb-8 text-sm leading-relaxed text-gray-500">
            Choose a new password for your account.
          </p>

          <form onSubmit={handleResetPassword} className="space-y-5">
            <div>
              <Input
                label="New Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password@123"
                required
                disabled={!uid || !token || messageType === "success"}
              />

              <p className="mt-2 text-xs leading-relaxed text-gray-500">
                Password must be at least 8 characters and include at least one
                letter, one digit, and one special character.
              </p>
            </div>

            <Input
              label="Confirm New Password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter your password"
              required
              disabled={!uid || !token || messageType === "success"}
            />

            {message && (
              <div
                className={`whitespace-pre-line rounded-lg p-3 text-sm font-medium ${
                  messageType === "success"
                    ? "bg-green-100 text-green-700"
                    : "bg-red-100 text-red-700"
                }`}
              >
                {message}
              </div>
            )}

            {messageType === "success" ? (
              <Link
                href="/login"
                className="block w-full rounded-lg bg-indigo-600 px-5 py-3 text-center font-semibold text-white hover:bg-indigo-700"
              >
                Go to Login
              </Link>
            ) : (
              <Button
                type="submit"
                fullWidth
                size="lg"
                isLoading={isLoading}
                disabled={!uid || !token}
              >
                Reset Password
              </Button>
            )}
          </form>
        </Card>
      </div>
    </main>
  );
}
