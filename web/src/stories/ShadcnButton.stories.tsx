import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "@/components/shadcn/button";

const meta: Meta<typeof Button> = {
  title: "Shadcn/Button",
  component: Button,
  parameters: { layout: "centered" },
  tags: ["autodocs"],
  argTypes: {
    variant: {
      control: "select",
      options: ["default", "destructive", "outline", "secondary", "ghost", "link", "fluid", "glass"],
    },
    size: {
      control: "select",
      options: ["default", "sm", "lg", "icon"],
    },
  },
};
export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { children: "Button", variant: "default" } };
export const Fluid: Story = { args: { children: "Fluid Button", variant: "fluid" } };
export const Glass: Story = { args: { children: "Glass Button", variant: "glass" } };
export const Secondary: Story = { args: { children: "Secondary", variant: "secondary" } };
export const Destructive: Story = { args: { children: "Destructive", variant: "destructive" } };
export const Outline: Story = { args: { children: "Outline", variant: "outline" } };
export const Ghost: Story = { args: { children: "Ghost", variant: "ghost" } };
export const Small: Story = { args: { children: "Small", size: "sm" } };
export const Large: Story = { args: { children: "Large", size: "lg" } };
