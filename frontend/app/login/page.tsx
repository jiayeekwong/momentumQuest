"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button, Card, Input } from "../../src/components/ui";
import { Logo } from "../../src/components/Logo";


export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("student@example.com");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [messageType, setMessageType] = useState<"success" | "error" | "">("");

  async function handleLogin(e: React.FormEvent) {
  e.preventDefault();

  setMessage("");
  setMessageType("");
  setIsLoading(true);

//Login logic
  try {
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/auth/login/`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      }
    );

    const data = await response.json();

    if (!response.ok) {
      setMessageType("error");

      if (
        data.detail === "No active account found with the given credentials" ||
        data.detail === "No active account found with the given credentials."
      ) {
        setMessage("Incorrect email or password. Please try again.");
      } else {
        setMessage(
          data.detail || "Login failed. Please check your email and password."
        );
      }

      return;
    }

    localStorage.setItem("accessToken", data.access);
    localStorage.setItem("refreshToken", data.refresh);

    const profileResponse = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/auth/profile/`,
      {
        method: "GET",
        headers: {
          Authorization: `Bearer ${data.access}`,
        },
      }
    );

    const profileData = await profileResponse.json();

    if (!profileResponse.ok) {
      setMessageType("error");
      setMessage("Failed to load user profile.");
      return;
    }

    localStorage.setItem("userRole", profileData.role);
    localStorage.setItem("userEmail", profileData.email);

    if (profileData.role === "STUDENT") {
      router.push("/dashboard");
    } else if (profileData.role === "COMPANY") {
      router.push("/company-dashboard");
    } else if (profileData.role === "ADMIN") {
      router.push("/admin-dashboard");
    } else {
      router.push("/");
    }
  } catch (error) {
    console.error("Login error:", error);
    setMessageType("error");
    setMessage("Something went wrong. Please make sure Django backend is running.");
  } finally {
    setIsLoading(false);
  }
}


//Design and structure of login page

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-600 to-sky-500 px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-8 flex flex-col items-center text-center">
          <Logo />
          <p className="mt-4 text-base font-semibold text-white/85">
            Accelerate your career journey
          </p>
        </div>

        <Card className="p-8">
          <h2 className="mb-8 text-3xl font-bold text-gray-950">
            Welcome back
          </h2>

          <form onSubmit={handleLogin} className="space-y-6">
            <Input
              label="Email Address"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="student@example.com"
              required
            />

            <div>
              <Input
                label="Password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
              />

              <div className="mt-3 text-right">
                <Link
                  href="/forgot-password"
                  className="text-sm font-semibold text-indigo-600 hover:underline"
                >
                  Forgot password?
                </Link>
              </div>
            </div>
 

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
              Login
            </Button>
          </form>

          <div className="mt-8 border-t border-gray-200 pt-6 text-center">
            <p className="text-sm text-gray-600">
              Don&apos;t have an account?{" "}
              <Link
                href="/signup"
                className="font-semibold text-indigo-600 hover:underline"
              >
                Sign up
              </Link>
            </p>
          </div>
        </Card>
      </div>
    </main>
  );
}