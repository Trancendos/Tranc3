import type { Meta, StoryObj } from "@storybook/react-vite";
import { Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter } from "@/components/shadcn/card";
import { Button } from "@/components/shadcn/button";
import { Badge } from "@/components/shadcn/badge";

const meta: Meta<typeof Card> = {
  title: "Shadcn/Card",
  component: Card,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
};
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {
  render: () => (
    <Card className="w-80">
      <CardHeader>
        <CardTitle>Platform Status</CardTitle>
        <CardDescription>All systems operational</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">Tranc3 backend running at 99.9% uptime.</p>
      </CardContent>
      <CardFooter>
        <Button size="sm">View Details</Button>
      </CardFooter>
    </Card>
  ),
};

export const GlassCard: Story = {
  render: () => (
    <div className="p-8 bg-background">
      <Card variant="glass" className="w-80">
        <CardHeader>
          <CardTitle>The Spark</CardTitle>
          <CardDescription>MCP Server — AI Tool Registry</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            <Badge variant="fluid">Active</Badge>
            <Badge variant="cell">Port 8000</Badge>
          </div>
        </CardContent>
      </Card>
    </div>
  ),
};

export const FluidCard: Story = {
  render: () => (
    <div className="p-8 bg-background">
      <Card variant="fluid" className="w-80">
        <CardHeader>
          <CardTitle>Luminous</CardTitle>
          <CardDescription>Core platform AI brain</CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm">Quantum-enhanced consciousness engine active.</p>
        </CardContent>
      </Card>
    </div>
  ),
};
