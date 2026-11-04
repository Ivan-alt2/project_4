from django.conf import settings
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, UpdateView

from blog.forms import CommentForm, PostForm, ProfileForm
from blog.models import Category, Comment, Post

User = get_user_model()


def get_published_posts():
    return (
        Post.objects.select_related('category', 'location', 'author')
        .filter(
            is_published=True,
            category__is_published=True,
            pub_date__lte=timezone.now(),
        )
        .annotate(comment_count=Count('comments'))
        .order_by('-pub_date')
    )


def index(request):
    template = 'blog/index.html'
    post_list = get_published_posts()
    paginator = Paginator(post_list, settings.LIMIT_POSTS)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, template, {'page_obj': page_obj})


def category_posts(request, category_slug):
    template = 'blog/category.html'
    category = get_object_or_404(
        Category, slug=category_slug, is_published=True
    )
    post_list = get_published_posts().filter(category=category)
    paginator = Paginator(post_list, settings.LIMIT_POSTS)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(
        request, template, {'category': category, 'page_obj': page_obj}
    )


def profile_view(request, username):
    profile = get_object_or_404(User, username=username)
    post_list = profile.posts.annotate(
        comment_count=Count('comments')
    ).order_by('-pub_date')
    if request.user.username != username:
        post_list = get_published_posts().filter(author=profile)

    paginator = Paginator(post_list, settings.LIMIT_POSTS)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(
        request,
        'blog/profile.html',
        {'profile': profile, 'page_obj': page_obj},
    )


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = 'blog/user.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse_lazy(
            'blog:profile', kwargs={'username': self.request.user.username}
        )


@login_required
def password_change_view(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, request.user)
            return redirect('blog:password_change_done')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'blog/password_change_form.html', {'form': form})


class PostMixin:
    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'


class PostCreateView(LoginRequiredMixin, PostMixin, CreateView):

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)


class PostUpdateView(
    LoginRequiredMixin, UserPassesTestMixin, PostMixin, UpdateView
):
    pk_url_kwarg = 'post_id'

    def test_func(self):
        return self.get_object().author == self.request.user

    def handle_no_permission(self):
        return redirect('blog:post_detail', self.kwargs['post_id'])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        return context


@login_required
def delete_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if post.author != request.user:
        return redirect('blog:post_detail', post_id)
    if request.method == 'POST':
        post.delete()
        return redirect('blog:profile', request.user.username)
    return render(
        request, 'blog/create.html', {'post': post, 'is_delete': True}
    )


class PostDetailView(DetailView):
    model = Post
    template_name = 'blog/detail.html'
    context_object_name = 'post'
    pk_url_kwarg = 'post_id'

    def get_object(self):
        post = super().get_object()
        is_visible = (
            post.is_published
            and post.category is not None
            and post.category.is_published
            and post.pub_date <= timezone.now()
        )
        if self.request.user != post.author and not is_visible:
            raise Http404()
        return post

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = CommentForm()
        context['comments'] = self.object.comments.select_related('author')
        return context


@login_required
def add_comment(request, post_id):
    post = get_object_or_404(
        Post,
        pk=post_id,
        is_published=True,
        pub_date__lte=timezone.now(),
    )
    form = CommentForm(request.POST)
    if form.is_valid():
        comment = form.save(commit=False)
        comment.author = request.user
        comment.post = post
        comment.save()
    return redirect('blog:post_detail', post_id)


@login_required
def edit_comment(request, post_id, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    if comment.author != request.user:
        return redirect('blog:post_detail', post_id)

    if request.method == 'POST':
        form = CommentForm(request.POST, instance=comment)
        if form.is_valid():
            form.save()
            return redirect('blog:post_detail', post_id)
    else:
        form = CommentForm(instance=comment)
    return render(
        request,
        'blog/comment.html',
        {'form': form, 'comment': comment, 'is_edit': True},
    )


@login_required
def delete_comment(request, post_id, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    if comment.author != request.user:
        return redirect('blog:post_detail', post_id)

    if request.method == 'POST':
        comment.delete()
        return redirect('blog:post_detail', post_id)
    return render(
        request, 'blog/comment.html', {'comment': comment, 'is_delete': True}
    )
