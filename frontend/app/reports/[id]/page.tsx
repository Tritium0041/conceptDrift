import { Shell } from "@/components/Shell";
import { ReportDetail } from "@/components/ReportDetail";

export default async function ReportPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const reportId = Number(id);

  return (
    <Shell>
      <ReportDetail reportId={reportId} />
    </Shell>
  );
}
