"use client";

import { ChevronRightIcon } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AuroraText } from "@/components/ui/aurora-text";
import { Button } from "@/components/ui/button";
import Galaxy from "@/components/ui/galaxy";
import { cn } from "@/lib/utils";

const HERO_WORDS = [
  "经营账号",
  "研究受众",
  "寻找选题",
  "写出脚本",
  "生成视频",
  "操作电脑",
  "发布复盘",
];

export function Hero({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "relative flex size-full flex-col items-center justify-center",
        className,
      )}
    >
      <div className="absolute inset-0 z-0 bg-black/55">
        <Galaxy
          mouseRepulsion={false}
          starSpeed={0.16}
          density={0.7}
          glowIntensity={0.4}
          twinkleIntensity={0.35}
          speed={0.42}
        />
      </div>
      <div className="container-md relative z-10 mx-auto flex min-h-svh flex-col items-center justify-center px-4 pt-20 pb-14">
        <div className="mb-6 rounded-full border border-white/15 bg-white/5 px-4 py-1.5 text-xs tracking-[0.2em] text-white/70 uppercase backdrop-blur">
          你的个人 IP 智能体
        </div>
        <h1 className="text-center text-5xl leading-tight font-bold break-words text-white md:text-7xl">
          IP Agent
        </h1>
        <div className="mt-4 flex w-full max-w-full min-w-0 items-center justify-center gap-x-2 text-center text-2xl font-semibold md:text-4xl">
          <HeroWordRotate words={HERO_WORDS} />
          <span className="whitespace-nowrap text-white">的本地智能体</span>
        </div>
        <p className="mt-8 max-w-3xl text-center text-base leading-8 text-white/65 sm:text-xl">
          你只说目标。它会理解账号和受众，完成研究、创作、视频生产、发布准备与复盘；
          需要你做创作判断或确认外部操作时，再请你介入。
        </p>
        <Link href="/workspace">
          <Button className="mt-9 h-11 px-5" size="lg">
            <span className="text-md">进入工作台</span>
            <ChevronRightIcon className="size-4" />
          </Button>
        </Link>
      </div>
    </div>
  );
}

function HeroWordRotate({
  words,
  duration = 2200,
}: {
  words: string[];
  duration?: number;
}) {
  const [index, setIndex] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setIndex((previous) => (previous + 1) % words.length);
    }, duration);
    return () => clearInterval(interval);
  }, [words, duration]);

  return (
    <div className="relative max-w-full min-w-0 overflow-hidden py-2">
      <AnimatePresence mode="popLayout">
        <motion.div
          key={index}
          className="max-w-full"
          initial={{ opacity: 0, y: -50, filter: "blur(16px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          exit={{ opacity: 0, y: 50, filter: "blur(16px)" }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        >
          <AuroraText
            className="max-w-full [overflow-wrap:anywhere] whitespace-normal"
            speed={3}
            colors={["#ffb86b", "#ff6b8a", "#8f7cff"]}
          >
            {words[index]}
          </AuroraText>
        </motion.div>
      </AnimatePresence>
    </div>
  );
}
