"use client";

import { useState } from "react";
import Link from "next/link";
import { Button, Card, Input } from "@/src/components/ui";
import { Logo } from "@/src/components/Logo";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error" | "">("");
  const [isLoading, setIsLoading] = useState(false);

  async function handleForgotPassword(e: React.FormEvent) {
    e.preventDefault();

    setMessage("");
    setMessageType("");

    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

    if (!emailRegex.test(email)) {
      setMessageType("error");
      setMessage("Please enter a valid email address.");
      return;
    }

    const blockedDomains = ["example.com", "test.com", "fake.com"];
    const emailDomain = email.split("@")[1]?.toLowerCase();

    if (blockedDomains.includes(emailDomain)) {
      setMessageType("error");
      setMessage("Please use a real email address, not a test email.");
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/auth/password-reset/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ email }),
        }
      );

      const data = await response.json();

      if (!response.ok) {
        setMessageType("error");
        setMessage(data.detail || "Unable to send reset email.");
        return;
      }

      setMessageType("success");
      setMessage(
        data.detail ||
          "If this email is registered, a password reset link will be sent to your email."
      );

      setEmail("");
    } catch (error) {
      console.error("Forgot password error:", error);
      setMessageType("error");
      setMessage("Something went wrong. Please try again.");
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
            Recover your MomentumQuest account
          </p>
        </div>

        <Card className="p-8">
          <h1 className="mb-2 text-3xl font-bold text-gray-950">
            Forgot password?
          </h1>

          <p className="mb-8 text-sm leading-relaxed text-gray-500">
            Enter the email address linked to your account. We will send you a
            password reset link if the email is registered.
          </p>

          <form onSubmit={handleForgotPassword} className="space-y-5">
            <Input
              label="Email Address"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="example@gmail.com"
              required
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

            <Button type="submit" fullWidth size="lg" isLoading={isLoading}>
              Send Reset Link
            </Button>
          </form>

          <div className="mt-8 border-t border-gray-200 pt-6 text-center">
            <p className="text-sm text-gray-600">
              Remember your password?{" "}
              <Link
                href="/login"
                className="font-semibold text-indigo-600 hover:underline"
              >
                Back to Login
              </Link>
            </p>
          </div>
        </Card>
      </div>
    </main>
  );
}
