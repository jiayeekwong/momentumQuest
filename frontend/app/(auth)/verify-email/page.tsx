"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";

export default function VerifyEmailPage() {
  const searchParams = useSearchParams();
  const [message, setMessage] = useState("Verifying your email...");
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    async function verifyEmail() {
      const uid = searchParams.get("uid");
      const token = searchParams.get("token");

      if (!uid || !token) {
        setMessage("Invalid verification link.");
        setSuccess(false);
        return;
      }

      try {
        const response = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL}/api/auth/verify-email/`,
          {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ uid, token }),
          }
        );

        const data = await response.json();

        if (response.ok) {
          setMessage(data.detail || "Email verified successfully.");
          setSuccess(true);
        } else {
          setMessage(data.detail || "Verification failed.");
          setSuccess(false);
        }
      } catch {
        setMessage("Something went wrong. Please try again.");
        setSuccess(false);
      }
    }

    verifyEmail();
  }, [searchParams]);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-600 to-sky-500 px-4">
      <div className="w-full max-w-md rounded-2xl bg-white p-8 text-center shadow-xl">
        <h1 className="text-2xl font-bold text-gray-900">Email Verification</h1>

        <p
          className={`mt-4 text-sm font-medium ${
            success ? "text-green-700" : "text-red-700"
          }`}
        >
          {message}
        </p>

        {success && (
          <Link
            href="/login"
            className="mt-6 inline-block rounded-lg bg-indigo-600 px-5 py-2 font-semibold text-white hover:bg-indigo-700"
          >
            Go to Login
          </Link>
        )}
      </div>
    </main>
  );
}
