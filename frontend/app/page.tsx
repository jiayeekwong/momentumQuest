import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-600 to-sky-500">
      <div className="text-center text-white">
        <h1 className="text-4xl font-bold">MomentumQuest</h1>
        <p className="mt-3">Accelerate your career journey</p>

        <div className="mt-6 flex justify-center gap-4">
          <Link
            href="/login"
            className="rounded-lg bg-white px-5 py-2 font-semibold text-indigo-600"
          >
            Login
          </Link>

          <Link
            href="/signup"
            className="rounded-lg border border-white px-5 py-2 font-semibold text-white"
          >
            Sign Up
          </Link>
        </div>
      </div>
    </main>
  );
}