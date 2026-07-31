// @ts-check
import { defineConfig } from "astro/config";
import starlight from "@astrojs/starlight";

// https://astro.build/config
export default defineConfig({
  site: "https://bbuchsbaum.github.io",
  base: "/rriscripts",
  integrations: [
    starlight({
      title: "rriscripts",
      description:
        "Tools for neuroimaging and SLURM-based HPC workflows: qexec, fmriprep, and xnat_cli.",
      social: [
        {
          icon: "github",
          label: "GitHub",
          href: "https://github.com/bbuchsbaum/rriscripts",
        },
      ],
      editLink: {
        baseUrl:
          "https://github.com/bbuchsbaum/rriscripts/edit/main/docs/",
      },
      customCss: ["./src/styles/custom.css"],
      lastUpdated: true,
      sidebar: [
        {
          label: "Start here",
          items: [
            { label: "Overview", slug: "index" },
            { label: "Installation", slug: "install" },
            { label: "Choosing a tool", slug: "choosing" },
          ],
        },
        {
          label: "qexec — SLURM submission",
          items: [
            { label: "Overview", slug: "qexec" },
            { label: "Workflows", slug: "qexec/workflows" },
            { label: "Packing and concurrency", slug: "qexec/packing" },
            { label: "cmd_expand syntax", slug: "qexec/cmd-expand" },
            { label: "Monitoring jobs", slug: "qexec/monitoring" },
            { label: "Reference", slug: "qexec/reference" },
          ],
        },
        {
          label: "fmriprep — launcher toolkit",
          items: [
            { label: "Overview", slug: "fmriprep" },
            { label: "Prerequisites", slug: "fmriprep/prerequisites" },
            { label: "Command-line workflow", slug: "fmriprep/workflow" },
            { label: "Subcommands", slug: "fmriprep/subcommands" },
            { label: "Configuration reference", slug: "fmriprep/configuration" },
            { label: "Cluster notes", slug: "fmriprep/cluster-notes" },
          ],
        },
        {
          label: "xnat_cli — XNAT from R",
          items: [
            { label: "Overview", slug: "xnat-cli" },
            { label: "Authentication", slug: "xnat-cli/authentication" },
            { label: "Browsing a repository", slug: "xnat-cli/browsing" },
            { label: "Downloading data", slug: "xnat-cli/downloading" },
            { label: "Reference", slug: "xnat-cli/reference" },
          ],
        },
      ],
    }),
  ],
});
