// Availability-schedule API client (authenticated).

import { authedFetch } from "@/lib/auth";

export type Rule = { weekday: number; start: string; end: string };
export type Override = {
  day: string;
  is_available: boolean;
  start: string | null;
  end: string | null;
};
export type Schedule = {
  id: string;
  name: string;
  timezone: string;
  rules: Rule[];
  overrides: Override[];
};

export type ScheduleInput = {
  name: string;
  timezone: string;
  rules: Rule[];
  overrides: Override[];
};

export function listSchedules(): Promise<Schedule[]> {
  return authedFetch<Schedule[]>("/v1/me/schedules");
}

export function createSchedule(body: ScheduleInput): Promise<{ id: string }> {
  return authedFetch<{ id: string }>("/v1/me/schedules", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateSchedule(id: string, body: ScheduleInput): Promise<Schedule> {
  return authedFetch<Schedule>(`/v1/me/schedules/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function deleteSchedule(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/schedules/${id}`, { method: "DELETE" });
}
