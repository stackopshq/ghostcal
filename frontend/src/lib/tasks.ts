// To-do tasks API client (zero-knowledge). The title/notes are sealed in the browser before they
// reach the server; the due date and completion state are cleartext (the server sorts/reminds).

import { authedFetch } from "@/lib/auth";

export type Task = {
  id: string;
  content: string | null; // sealed {title, notes} blob
  due_at: string | null;
  completed: boolean;
  completed_at: string | null;
  created_at: string;
};

export type TaskInput = {
  content: string | null;
  due_at: string | null;
};

export function listTasks(): Promise<Task[]> {
  return authedFetch<Task[]>("/v1/me/tasks");
}

export function createTask(body: TaskInput): Promise<{ id: string }> {
  return authedFetch<{ id: string }>("/v1/me/tasks", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function updateTask(id: string, body: TaskInput): Promise<void> {
  return authedFetch<void>(`/v1/me/tasks/${id}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

export function completeTask(id: string, completed: boolean): Promise<void> {
  return authedFetch<void>(`/v1/me/tasks/${id}/complete`, {
    method: "POST",
    body: JSON.stringify({ completed }),
  });
}

export function deleteTask(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/tasks/${id}`, { method: "DELETE" });
}
