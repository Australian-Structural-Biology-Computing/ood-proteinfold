#!/usr/bin/env ruby
# frozen_string_literal: true

require "erb"
require "open3"
require "ostruct"
require "pathname"
require "yaml"

ROOT = Pathname(__dir__).join("..").expand_path

REQUIRED_FILES = %w[
  manifest.yml
  form.yml.erb
  submit.yml.erb
  info.html.erb
  view.html.erb
  template/script.sh.erb
].freeze

class TemplateContext
  attr_reader :context

  def initialize
    @context = OpenStruct.new(
      run_name: "ci_run",
      query_fasta: "/tmp/query.fasta",
      target_fasta: "/tmp/target.fasta",
      workflow: "proteindj",
      target: "/tmp/target.pdb",
      target_chain: "A",
      hotspots: "10,20,30",
      minlen: 60,
      maxlen: 100,
      ndesigns: 10,
      seqs_per_design: 4,
      pdj_seq_method: "mpnn",
      pdj_pred_method: "boltz",
      mpnn_relax_max_cycles: 1,
      uncropped_target_pdb: "",
      boltz_use_templates: "false",
      boltz_input_msa: "",
      fold_min_ss: 3,
      seq_min_ext_coef: 1000,
      max_designs: 10,
      max_seqs_per_fold: 2,
      af2_max_pae_interaction: 10,
      af2_min_plddt_overall: 70,
      af2_max_rmsd_binder_bndaln: 2,
      af2_max_rmsd_binder_tgtaln: 2,
      boltz_max_rmsd_binder: 2,
      boltz_max_rmsd_target: 2,
      boltz_max_rmsd_overall: 2,
      boltz_min_ptm_interface: 0.5,
      samplesheet: "/tmp/samplesheet.csv",
      af_method: "colabfold",
      prot_mode: "monomer_ptm",
      full_dbs: "reduced",
      colabfold_num_recycles: 3,
      esmfold_num_recycles: 4,
      boltz_use_potentials: "false",
      msa_server: "local"
    )
  end

  def get_binding
    run_name = "ci_run"
    af_method = "colabfold"
    msa_server = "local"
    workflow = "proteindj"
    email = "ci@example.com"
    email_on_terminated = false
    base_out_dir = "/tmp/ood-results"
    results_url_base = "/pun/sys/dashboard/files/fs"
    run_dir = "ci_run"
    user = "ci-user"
    session_output_dir = "/tmp/ood-session"
    context = @context
    binding
  end
end

def assert_required_files!
  missing = REQUIRED_FILES.reject { |relative_path| ROOT.join(relative_path).exist? }
  return if missing.empty?

  abort("Missing required app files:\n- #{missing.join("\n- ")}")
end

def erb_templates
  Dir.glob(ROOT.join("**/*.erb")).sort
end

def compile_erb!(path)
  source = File.read(path)
  compiled = ERB.new(source).src
  RubyVM::InstructionSequence.compile(compiled, path)
rescue StandardError => e
  abort("ERB compilation failed for #{Pathname(path).relative_path_from(ROOT)}: #{e.message}")
end

def render_template(path, template_context)
  ERB.new(File.read(path), trim_mode: "-").result(template_context.get_binding)
end

def validate_yaml_file!(relative_path, template_context)
  rendered = render_template(ROOT.join(relative_path), template_context)
  YAML.safe_load(rendered, aliases: true)
rescue StandardError => e
  abort("YAML validation failed for #{relative_path}: #{e.message}")
end

def validate_manifest!
  YAML.safe_load_file(ROOT.join("manifest.yml"), aliases: true)
rescue StandardError => e
  abort("YAML validation failed for manifest.yml: #{e.message}")
end

def validate_shell_templates!(template_context)
  Dir.glob(ROOT.join("template/*.sh.erb")).sort.each do |path|
    rendered = render_template(path, template_context)
    _stdout, stderr, status = Open3.capture3("bash", "-n", stdin_data: rendered)
    next if status.success?

    relative_path = Pathname(path).relative_path_from(ROOT)
    abort("Shell validation failed for #{relative_path}: #{stderr.strip}")
  end
end

assert_required_files!
validate_manifest!

template_context = TemplateContext.new
erb_templates.each { |path| compile_erb!(path) }
validate_yaml_file!("form.yml.erb", template_context)
validate_yaml_file!("submit.yml.erb", template_context)
validate_shell_templates!(template_context)

puts "Open OnDemand app validation passed for #{ROOT.basename}"
