"use client";

import { FlaskConicalIcon, PlayIcon, SaveIcon, Trash2Icon } from "lucide-react";
import { io } from "next/cache";
import { use, useState } from "react";

import { useReviewToday } from "@/components/reviews/weekly-review-page";
import { ScenarioForm } from "@/components/simulator/scenario-form";
import { SimulationResults } from "@/components/simulator/simulation-results";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useApiData } from "@/hooks/use-api-data";
import {
  apiRequest,
  describeError,
  withQuery,
  type Category,
  type GoalList,
  type Scenario,
  type ScenarioCreate,
  type ScenarioList,
  type SimulationParam,
  type SimulationRequest,
  type SimulationResult,
} from "@/lib/api";
import { formatDate, formatSignedVND } from "@/lib/format";
import { fromParam, newRow, toParam, type ParamRow } from "@/lib/simulator";

/**
 * `/simulator` (Phase 17): thử kịch bản what-if (giảm chi danh mục, đổi thu nhập, thêm khoản định
 * kỳ, đổi hạn mục tiêu) trên mức trung bình các tháng gần nhất — **không** thay đổi dữ liệu thật.
 * `?today=YYYY-MM-DD` (tuỳ chọn) đặt "hôm nay" như các trang review.
 */
export function SimulatorPage() {
  use(io());
  const today = useReviewToday();
  const categories = useApiData<Category[]>(
    withQuery("/categories", { kind: "expense" }),
  );
  const goals = useApiData<GoalList>(
    withQuery("/goals", { today, status: "active" }),
  );
  const saved = useApiData<ScenarioList>("/simulator/scenarios");

  const [rows, setRows] = useState<ParamRow[]>(() => [newRow("reduce_category", "initial")]);
  const [months, setMonths] = useState("3");
  const [includeIrregular, setIncludeIrregular] = useState(false);
  const [withNarrative, setWithNarrative] = useState(true);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [name, setName] = useState("");
  const [saveMessage, setSaveMessage] = useState<string | null>(null);

  function buildParams(): SimulationParam[] | null {
    const params: SimulationParam[] = [];
    for (const [i, row] of rows.entries()) {
      const param = toParam(row);
      if (typeof param === "string") {
        setError(`Thay đổi ${i + 1}: ${param}`);
        return null;
      }
      params.push(param);
    }
    return params;
  }

  async function run(paramsOverride?: SimulationParam[]) {
    setError(null);
    setSaveMessage(null);
    const params = paramsOverride ?? buildParams();
    if (!params) return;
    setRunning(true);
    try {
      const body: SimulationRequest = {
        params,
        baseline_months: Number(months),
        include_irregular: includeIrregular,
        with_narrative: withNarrative,
      };
      setResult(
        await apiRequest<SimulationResult>(
          "POST",
          withQuery("/simulator/run", { today }),
          body,
        ),
      );
    } catch (err) {
      setError(describeError(err));
    } finally {
      setRunning(false);
    }
  }

  async function save() {
    setSaveMessage(null);
    const params = buildParams();
    if (!params || !name.trim()) {
      if (!name.trim()) setSaveMessage("Đặt tên cho kịch bản trước khi lưu.");
      return;
    }
    try {
      const body: ScenarioCreate = {
        name: name.trim(),
        params,
        baseline_months: Number(months),
        include_irregular: includeIrregular,
      };
      await apiRequest<Scenario>(
        "POST",
        withQuery("/simulator/scenarios", { today }),
        body,
      );
      setSaveMessage(`Đã lưu “${name.trim()}”.`);
      setName("");
      saved.reload();
    } catch (err) {
      setSaveMessage(describeError(err));
    }
  }

  async function remove(scenario: Scenario) {
    try {
      await apiRequest("DELETE", `/simulator/scenarios/${scenario.id}`);
      saved.reload();
    } catch (err) {
      setSaveMessage(describeError(err));
    }
  }

  function open(scenario: Scenario) {
    setRows(scenario.params.params.map(fromParam));
    setMonths(String(scenario.params.baseline_months));
    setIncludeIrregular(scenario.params.include_irregular ?? false);
    void run(scenario.params.params);
  }

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="flex items-center gap-2 font-heading text-2xl font-semibold">
          <FlaskConicalIcon className="size-6" />
          Mô phỏng What-if
        </h1>
        <p className="text-sm text-muted-foreground">
          Thử “nếu… thì sao?” trên mức chi tiêu trung bình gần đây và xem tác
          động tới tiền để dành mỗi tháng, ngày đạt mục tiêu và ngân sách.
        </p>
      </div>

      <p
        role="note"
        className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-2 text-sm text-sky-900 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-200"
      >
        Đây là <strong>mô phỏng</strong> — không thay đổi giao dịch, ngân sách
        hay mục tiêu thật của bạn. Muốn áp dụng, hãy tự chỉnh ở trang Ngân sách
        / Mục tiêu.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Kịch bản</CardTitle>
          <CardDescription>
            Các thay đổi được áp dụng lần lượt từ trên xuống.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ScenarioForm
            rows={rows}
            onChange={setRows}
            categories={categories.data ?? []}
            goals={goals.data?.items ?? []}
            today={today}
          />
          <div className="flex flex-wrap items-end gap-4 text-sm">
            <div className="flex w-36 flex-col gap-1.5">
              <Label htmlFor="sim-months">Mức nền (tháng)</Label>
              <Input
                id="sim-months"
                type="number"
                min={1}
                max={12}
                value={months}
                onChange={(e) => setMonths(e.target.value)}
              />
            </div>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={includeIrregular}
                onChange={(e) => setIncludeIrregular(e.target.checked)}
              />
              Tính cả khoản bất thường
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={withNarrative}
                onChange={(e) => setWithNarrative(e.target.checked)}
              />
              Diễn giải bằng AI
            </label>
            <Button type="button" onClick={() => void run()} disabled={running}>
              <PlayIcon data-icon="inline-start" />
              {running ? "Đang mô phỏng…" : "Chạy mô phỏng"}
            </Button>
          </div>
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
        </CardContent>
      </Card>

      {result && (
        <>
          <SimulationResults result={result} />
          <Card size="sm">
            <CardContent className="flex flex-wrap items-end gap-3">
              <div className="flex min-w-60 flex-1 flex-col gap-1.5">
                <Label htmlFor="sim-name">Lưu kịch bản</Label>
                <Input
                  id="sim-name"
                  value={name}
                  maxLength={100}
                  placeholder="Giảm ăn ngoài 20%"
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <Button
                type="button"
                variant="outline"
                onClick={() => void save()}
              >
                <SaveIcon data-icon="inline-start" />
                Lưu kịch bản
              </Button>
              {saveMessage && <span className="text-sm">{saveMessage}</span>}
            </CardContent>
          </Card>
        </>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Kịch bản đã lưu</CardTitle>
          <CardDescription>
            Kết quả hiển thị là lúc lưu; mở lại để mô phỏng với số liệu mới.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {saved.error && (
            <p className="text-sm text-destructive">
              {describeError(saved.error)}
            </p>
          )}
          {saved.data && saved.data.items.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Chưa có kịch bản nào.
            </p>
          )}
          <ul className="flex flex-col divide-y">
            {saved.data?.items.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center gap-3 py-2">
                <div className="min-w-48 flex-1">
                  <p className="font-medium">{s.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {s.result.applied.map((a) => a.label).join(" · ")} — lưu{" "}
                    {formatDate(s.created_at.slice(0, 10))}
                  </p>
                </div>
                <span className="text-sm tabular-nums">
                  {formatSignedVND(s.result.delta_monthly_savings)} / tháng
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => open(s)}
                >
                  Mở
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  aria-label={`Xoá kịch bản ${s.name}`}
                  onClick={() => void remove(s)}
                >
                  <Trash2Icon />
                </Button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
