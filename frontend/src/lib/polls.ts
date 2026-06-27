// Host meeting-poll API client.

import { authedFetch } from "@/lib/auth";

export type PollOption = { id: string; start_at: string; end_at: string; votes: number };
export type Voter = { name: string; email: string; option_ids: string[] };

export type Poll = {
  id: string;
  slug: string;
  title: string;
  duration_min: number;
  location_type: string;
  status: string;
  owner_name: string;
  finalized_option_id: string | null;
  options: PollOption[];
  voters: Voter[];
};

export type PollSummary = {
  id: string;
  slug: string;
  title: string;
  status: string;
  option_count: number;
  vote_count: number;
};

export function listPolls(): Promise<PollSummary[]> {
  return authedFetch<PollSummary[]>("/v1/me/polls");
}

export function getPoll(id: string): Promise<Poll> {
  return authedFetch<Poll>(`/v1/me/polls/${id}`);
}

export function createPoll(body: {
  title: string;
  duration_min: number;
  location_type: string;
  option_starts: string[];
}): Promise<Poll> {
  return authedFetch<Poll>("/v1/me/polls", { method: "POST", body: JSON.stringify(body) });
}

export function finalizePoll(id: string, optionId: string): Promise<Poll> {
  return authedFetch<Poll>(`/v1/me/polls/${id}/finalize`, {
    method: "POST",
    body: JSON.stringify({ option_id: optionId }),
  });
}

export function cancelPoll(id: string): Promise<void> {
  return authedFetch<void>(`/v1/me/polls/${id}`, { method: "DELETE" });
}
