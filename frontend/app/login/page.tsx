"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Button, Card, Input } from "../../src/components/ui";
import { Logo } from "../../src/components/Logo";

type LoginRole = "student" | "company" | "admin";

export default function LoginPage() {
  const router = useRouter();

  const [email, setEmail] = useState("student@example.com");
  const [password, setPassword] = useState("");
  const [selectedRole, setSelectedRole] = useState<LoginRole>("student");
  const [isLoading, setIsLoading] = useState(false);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setIsLoading(true);

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
        alert("Login failed. Please check your email and password.");
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
        alert("Failed to get user profile.");
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
      alert("Something went wrong. Please make sure Django backend is running.");
    } finally {
      setIsLoading(false);
    }
  }

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

            <div>
              <label className="mb-3 block text-sm font-semibold text-gray-900">
                Sign in as
              </label>

              <div className="grid grid-cols-3 rounded-full bg-gray-100 p-1">
                {(["student", "company", "admin"] as LoginRole[]).map(
                  (role) => (
                    <button
                      key={role}
                      type="button"
                      onClick={() => setSelectedRole(role)}
                      className={`rounded-full px-3 py-2 text-sm font-semibold capitalize transition ${
                        selectedRole === role
                          ? "bg-white text-indigo-600 shadow"
                          : "text-gray-700 hover:text-gray-950"
                      }`}
                    >
                      {role}
                    </button>
                  )
                )}
              </div>
            </div>

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