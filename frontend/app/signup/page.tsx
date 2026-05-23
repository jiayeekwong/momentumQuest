"use client";

import { useState } from "react";
import Link from "next/link";
import { Button, Card, Input } from "../../src/components/ui";
import { Logo } from "../../src/components/Logo";

type SignupRole = "STUDENT" | "COMPANY";
type ApiErrorResponse = {
  detail?: string | string[];
  [key: string]: unknown;
};

export default function SignupPage() {
  const [role, setRole] = useState<SignupRole>("STUDENT");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [department, setDepartment] = useState("");
  const [desiredJobCategory, setDesiredJobCategory] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error" | "">("");
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

  async function handleSignup(e: React.FormEvent) {
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

    if (!process.env.NEXT_PUBLIC_API_URL) {
      setMessageType("error");
      setMessage("API URL is missing. Please check your .env.local file.");
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/auth/register/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            email,
            password,
            confirm_password: confirmPassword,
            role,
            name,
            department: role === "STUDENT" ? department : "",
            desired_job_category:
              role === "STUDENT" ? desiredJobCategory : "",
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
      setMessage(
        "Registration successful. Please check your email to verify your account before logging in."
      );

      setName("");
      setEmail("");
      setDepartment("");
      setDesiredJobCategory("");
      setPassword("");
      setConfirmPassword("");
    } catch (error) {
      console.error("Signup error:", error);
      setMessageType("error");
      setMessage(
        "Signup failed. Please make sure the Django backend is running."
      );
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-600 to-sky-500 px-4 py-10">
      <div className="w-full max-w-lg">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo />

          <p className="mt-4 text-base font-semibold text-white/85">
            Start your career journey with MomentumQuest
          </p>
        </div>

        <Card className="p-8">
          <h1 className="mb-2 text-3xl font-bold text-gray-950">
            Create account
          </h1>

          <p className="mb-8 text-sm text-gray-500">
            Sign up as a student or company to continue.
          </p>

          <form onSubmit={handleSignup} className="space-y-5">
            <div>
              <label className="mb-3 block text-sm font-semibold text-gray-900">
                Register as
              </label>

              <div className="grid grid-cols-2 rounded-full bg-gray-100 p-1">
                {(["STUDENT", "COMPANY"] as SignupRole[]).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setRole(item)}
                    className={`rounded-full px-3 py-2 text-sm font-semibold transition ${
                      role === item
                        ? "bg-white text-indigo-600 shadow"
                        : "text-gray-700 hover:text-gray-950"
                    }`}
                  >
                    {item === "STUDENT" ? "Student" : "Company"}
                  </button>
                ))}
              </div>
            </div>

            <Input
              label={role === "COMPANY" ? "Company Name" : "Full Name"}
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={role === "COMPANY" ? "ABC Tech Sdn Bhd" : "Jia Yee"}
              required
            />

            <Input
              label="Email Address"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="example@gmail.com"
              required
            />

            {role === "STUDENT" && (
              <>
                <Input
                  label="Department"
                  type="text"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  placeholder="Software Engineering"
                />

                <Input
                  label="Desired Job Category"
                  type="text"
                  value={desiredJobCategory}
                  onChange={(e) => setDesiredJobCategory(e.target.value)}
                  placeholder="Web Developer"
                />
              </>
            )}

            <div>
              <Input
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Password@123"
                required
              />

              <p className="mt-2 text-xs leading-relaxed text-gray-500">
                Password must be at least 8 characters and include at least one
                letter, one digit, and one special character.
              </p>
            </div>

            <Input
              label="Confirm Password"
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Re-enter your password"
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
              Sign Up
            </Button>
          </form>

          <div className="mt-8 border-t border-gray-200 pt-6 text-center">
            <p className="text-sm text-gray-600">
              Already have an account?{" "}
              <Link
                href="/login"
                className="font-semibold text-indigo-600 hover:underline"
              >
                Login
              </Link>
            </p>
          </div>
        </Card>
      </div>
    </main>
  );
}
