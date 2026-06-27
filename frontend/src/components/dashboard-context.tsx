"use client";

import { createContext, useContext } from "react";
import type { User } from "@/lib/auth";

export const DashboardUserContext = createContext<User | null>(null);

export function useDashboardUser(): User | null {
  return useContext(DashboardUserContext);
}
