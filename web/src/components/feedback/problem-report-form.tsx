"use client"

import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import * as z from "zod"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card"
import { Textarea } from "@/components/ui/textarea"
import { Input } from "@/components/ui/input"
import { Checkbox } from "@/components/ui/checkbox"
import {
  Field,
  FieldLabel,
  FieldDescription,
  FieldError,
  FieldGroup,
  FieldSet,
  FieldLegend,
} from "@/components/ui/form"
import { BugIcon } from "lucide-react"

const categories = [
  { id: "bug", label: "Bug" },
  { id: "data", label: "Data issue" },
  { id: "feature", label: "Feature request" },
  { id: "ui", label: "UI/UX" },
  { id: "performance", label: "Performance" },
  { id: "other", label: "Other" },
] as const

type CategoryId = (typeof categories)[number]["id"]

const problemReportSchema = z.object({
  categories: z
    .array(z.string())
    .min(1, "Please select at least one category."),
  description: z
    .string()
    .min(10, "Description must be at least 10 characters.")
    .max(1000, "Description must be at most 1000 characters."),
  contactInfo: z
    .string()
    .max(100, "Contact info must be at most 100 characters.")
    .optional(),
})

type ProblemReportValues = z.infer<typeof problemReportSchema>

export function ProblemReportForm() {
  const form = useForm<ProblemReportValues>({
    resolver: zodResolver(problemReportSchema),
    defaultValues: {
      categories: [],
      description: "",
      contactInfo: "",
    },
  })

  function onSubmit(data: ProblemReportValues) {
    console.log("Problem report submitted:", data)
    form.reset()
  }

  return (
    <Card className="flex flex-col">
      <CardHeader>
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-full bg-destructive/10 text-destructive">
            <BugIcon className="size-4" />
          </div>
          <CardTitle>Report a Problem / Issue</CardTitle>
        </div>
        <CardDescription>
          Found a bug or have feedback? Let us know so we can fix it.
        </CardDescription>
      </CardHeader>

      <CardContent>
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          noValidate
          className="flex flex-col gap-4"
        >
          {/* Category checkboxes */}
          <Controller
            name="categories"
            control={form.control}
            render={({ field, fieldState }) => (
              <FieldSet>
                <FieldLegend variant="label">Category</FieldLegend>
                <FieldDescription className="mt-2">
                  Select all that apply to your issue.
                </FieldDescription>
                <FieldGroup
                  data-slot="checkbox-group"
                  className="flex flex-wrap flex-row gap-x-4 gap-y-2"
                >
                  {categories.map((cat) => (
                    <Field
                      key={cat.id}
                      orientation="horizontal"
                      className="gap-2"
                      data-invalid={fieldState.invalid || undefined}
                    >
                      <Checkbox
                        id={`problem-cat-${cat.id}`}
                        aria-invalid={fieldState.invalid || undefined}
                        checked={field.value.includes(cat.id)}
                        onCheckedChange={(checked) => {
                          const next = checked
                            ? [...field.value, cat.id]
                            : field.value.filter((v) => v !== cat.id)
                          field.onChange(next)
                        }}
                      />
                      <FieldLabel
                        htmlFor={`problem-cat-${cat.id}`}
                        className="font-normal"
                      >
                        {cat.label}
                      </FieldLabel>
                    </Field>
                  ))}
                </FieldGroup>
                {fieldState.invalid && (
                  <FieldError errors={[fieldState.error]} />
                )}
              </FieldSet>
            )}
          />

          {/* Description */}
          <Controller
            name="description"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid || undefined}>
                <FieldLabel htmlFor={field.name}>Description</FieldLabel>
                <Textarea
                  {...field}
                  id={field.name}
                  aria-invalid={fieldState.invalid || undefined}
                  placeholder="Describe the problem in detail. What did you expect to happen? What actually happened?"
                  className="min-h-[120px]"
                />
                {fieldState.invalid && (
                  <FieldError errors={[fieldState.error]} />
                )}
              </Field>
            )}
          />

          {/* Contact info */}
          <Controller
            name="contactInfo"
            control={form.control}
            render={({ field, fieldState }) => (
              <Field data-invalid={fieldState.invalid || undefined}>
                <FieldLabel htmlFor={field.name}>
                  Contact info{" "}
                  <span className="font-normal text-muted-foreground">
                    (optional)
                  </span>
                </FieldLabel>
                <Input
                  {...field}
                  id={field.name}
                  aria-invalid={fieldState.invalid || undefined}
                  placeholder="email@example.com or @handle"
                  autoComplete="email"
                />
                <FieldDescription>
                  Leave your contact info if you&apos;d like a follow-up.
                </FieldDescription>
                {fieldState.invalid && (
                  <FieldError errors={[fieldState.error]} />
                )}
              </Field>
            )}
          />

          <div className="flex gap-2 pt-2">
            <Button type="submit" className="flex-1">
              Submit Problem
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => form.reset()}
            >
              Reset
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  )
}
