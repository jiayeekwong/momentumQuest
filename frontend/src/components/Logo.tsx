import Image from "next/image";

export function Logo() {
  return (
    <div className="flex flex-col items-center">
      <Image
        src="/momentumquest-logo.png"
        alt="MomentumQuest Logo"
        width={140}
        height={140}
        priority
        className="h-auto w-36 object-contain"
      />

      <h1 className="mt-4 text-4xl font-extrabold tracking-wide text-white">
        MOMENTUMQUEST
      </h1>
    </div>
  );
}